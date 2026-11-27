from datetime import datetime, timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB


@tagged("post_install", "-at_install")
class TestBalanceDue(OrderCase):
    """Sales sets on the quotation when the balance after a 30 % advance is due; neither choice holds back collection,
    and the report waits for it whatever the choice."""

    def confirmed(self, balance_due=None):
        order = self.make_quotable_order()
        order.write({"advance_mode": "percentage", "advance_value": 30})
        if balance_due:
            order.balance_due = balance_due
        order.with_user(self.sales).action_send_quotation()
        self.pay_advance(order)
        order.with_user(self.sales).action_confirm_order()
        return order

    def test_a_portal_order_owes_its_balance_before_the_report_and_its_samples_are_collected_at_once(self):
        self.route_collection_to_delivery_staff()
        order = self.confirmed()

        self.assertEqual(order.source, "portal")
        self.assertEqual(order.balance_due, "before_report")
        self.assertNotEqual(order.payment_status, "paid")
        self.assertEqual(order.test_request_id.status, "paid")
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
        self.assertIn(due, task.note or "")
        self.assertIn("paid in full", order.payment_notice or "")

    def test_a_balance_due_before_the_report_leaves_collection_free_of_payment(self):
        self.route_collection_to_delivery_staff()
        order = self.confirmed("before_report")

        self.assertFalse(order.show_unpaid_warning)
        order.with_user(self.sales).action_start_sample_collection()

        self.assertNotIn("Balance due", self.collection_tasks(order).note or "")

    def test_a_verified_advance_lets_the_request_receive_samples_before_the_balance(self):
        order = self.confirmed("before_report")
        request = order.test_request_id
        self.assertEqual(request.status, "paid")

        request.sample_ids[:1].with_user(self.sales).sudo().action_receive(1, "good")

        self.assertEqual(request.status, "sample_received")

    def test_a_received_order_shows_no_collection_hold(self):
        order = self.confirmed("at_collection")
        order.test_request_id.status = "sample_received"
        order.invalidate_recordset(["show_unpaid_warning", "payment_notice"])

        self.assertFalse(order.show_unpaid_warning)
        self.assertIn("paid in full", order.payment_notice or "")

    def test_the_balance_timing_stays_as_quoted(self):
        order = self.sent_order()

        with self.assertRaises(UserError):
            order.with_user(self.sales).balance_due = "at_collection"

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
