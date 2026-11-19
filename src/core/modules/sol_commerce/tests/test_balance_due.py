from datetime import datetime, timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB


@tagged("post_install", "-at_install")
class TestBalanceDue(OrderCase):
    """Sales sets on the quotation when the balance after a 30 % advance is due; the report waits for it whatever the
    choice."""

    def confirmed(self, balance_due):
        order = self.make_quotable_order()
        order.write({"advance_mode": "percentage", "advance_value": 30, "balance_due": balance_due})
        order.with_user(self.sales).action_send_quotation()
        self.pay_advance(order)
        order.with_user(self.sales).action_confirm_order()
        return order

    def test_a_balance_due_before_collection_holds_the_collection_until_it_is_paid(self):
        self.route_collection_to_delivery_staff()
        order = self.confirmed("before_collection")

        self.assertTrue(order.show_unpaid_warning)
        with self.assertRaisesRegex(UserError, "Verify the order balance"):
            order.with_user(self.sales).action_start_sample_collection()

        self.pay_advance(order)
        order.invalidate_recordset(["payment_status", "show_unpaid_warning"])

        self.assertFalse(order.show_unpaid_warning)
        order.with_user(self.sales).action_start_sample_collection()
        self.assertTrue(self.collection_tasks(order))

    def test_a_balance_due_at_collection_goes_on_the_collection_task(self):
        self.route_collection_to_delivery_staff()
        order = self.confirmed("at_collection")
        due = order.currency_id.format(order.payment_request_id.remaining_amount)

        order.with_user(self.sales).action_start_sample_collection(address="Gate 3, 45 Le Loi")

        task = self.collection_tasks(order)
        self.assertEqual(task.place, "Gate 3, 45 Le Loi")
        self.assertIn(due, task.note)
        self.assertIn("paid in full", order.payment_notice)

    def test_a_balance_due_before_the_report_leaves_collection_free_of_payment(self):
        self.route_collection_to_delivery_staff()
        order = self.confirmed("before_report")

        self.assertFalse(order.show_unpaid_warning)
        order.with_user(self.sales).action_start_sample_collection()

        self.assertFalse(self.collection_tasks(order).note)

    def test_the_balance_timing_stays_as_quoted(self):
        order = self.sent_order()

        with self.assertRaises(UserError):
            order.with_user(self.sales).balance_due = "before_collection"

    def test_an_unclaimed_collection_due_within_a_day_is_raised_with_the_salesperson(self):
        self.route_collection_to_delivery_staff()
        order = self.confirmed("before_report")
        appointment = fields.Datetime.now() + timedelta(hours=5)
        order.with_user(self.sales).action_start_sample_collection(appointment=appointment)
        jobs = self.env[MODEL_SCHEDULED_JOB]

        jobs._queue_collections_unclaimed()
        item = self.env["medilab.job.item"].search([("item_key", "like", f"{self.collection_tasks(order).id}:%")])
        jobs._handle_collections_unclaimed(item)

        notice = order.message_ids.filtered(lambda message: "Nobody has claimed" in (message.body or ""))
        self.assertTrue(notice)
        self.assertEqual(notice.partner_ids, self.sales.partner_id)

    def test_a_collection_due_later_is_not_raised(self):
        self.route_collection_to_delivery_staff()
        order = self.confirmed("before_report")
        order.with_user(self.sales).action_start_sample_collection(appointment=datetime.now() + timedelta(days=3))

        self.env[MODEL_SCHEDULED_JOB]._queue_collections_unclaimed()

        self.assertFalse(
            self.env["medilab.job.item"].search([("item_key", "like", f"{self.collection_tasks(order).id}:%")])
        )
