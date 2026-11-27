from datetime import datetime, timedelta
from pathlib import Path

from odoo import fields
from odoo.exceptions import UserError
from odoo.modules.module import load_script
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

    def test_a_verified_advance_releases_collection_while_the_portal_balance_is_open(self):
        staff = self.route_collection_to_delivery_staff()
        order = self.confirmed("before_collection")
        request = order.test_request_id
        balance = order.payment_request_id

        self.assertEqual(request.status, "paid")
        self.assertFalse(order.show_unpaid_warning)
        order.with_user(self.sales).action_start_sample_collection()
        self.assertTrue(self.collection_tasks(order))
        request.sample_ids.with_user(staff.user_id).sudo().action_receive("500 ml", "good")
        self.assertEqual(request.status, "sample_received")
        self.assertEqual((balance.kind, balance.state), ("balance", "open"))
        self.assertAlmostEqual(balance.remaining_amount, order.amount_total * 0.7)
        self.assertTrue(order._withholds_report())

    def test_upgrade_releases_only_orders_whose_advance_is_verified(self):
        funded = self.confirmed("before_collection")
        unpaid = self.confirmed("before_collection")
        funded.test_request_id.status = "confirmed"
        unpaid.test_request_id.status = "confirmed"
        unpaid.payment_request_ids.filtered(lambda ask: ask.kind == "advance").state = "open"
        self.env.flush_all()

        path = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.24.0" / "post-migrate.py"
        migrate = load_script(str(path), "release_funded_advances").migrate
        migrate(self.env.cr, "20.0.1.23.0")
        migrate(self.env.cr, "20.0.1.23.0")
        self.env.invalidate_all()

        self.assertEqual(funded.test_request_id.status, "paid")
        self.assertEqual(funded.payment_request_id.state, "open")
        self.assertEqual(unpaid.test_request_id.status, "confirmed")
        unpaid.payment_request_ids.filtered(lambda ask: ask.kind == "advance")._refresh_funding()
        self.assertEqual(unpaid.test_request_id.status, "paid")
        self.assertEqual(unpaid.payment_request_id.state, "open")

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
        order = self.confirmed("before_collection")
        order.test_request_id.status = "sample_received"
        order.invalidate_recordset(["show_unpaid_warning", "payment_notice"])

        self.assertFalse(order.show_unpaid_warning)
        self.assertIn("paid in full", order.payment_notice or "")

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
