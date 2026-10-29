from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_laboratory.constants.models import MODEL_TASK


@tagged("post_install", "-at_install")
class TestOrderCancellation(OrderCase):
    def test_customer_cancel_until_confirmed(self):
        draft = self.make_order([(self.lead_product, 1)])
        confirmed = self.make_order([(self.lead_product, 1)], status="confirmed", user_id=self.sales.id)

        self.assertEqual(draft.customer_cancel_mode(), "cancel")
        self.assertEqual(confirmed.customer_cancel_mode(), "request")
        draft.with_user(self.portal).action_customer_cancel()
        with self.assertRaises(UserError):
            confirmed.with_user(self.portal).action_customer_cancel()

        self.assertEqual(draft.order_status, "cancelled")
        self.assertEqual(draft.state, "cancel")
        self.assertEqual(confirmed.order_status, "confirmed")

    def test_request_needs_a_reason_and_decline_keeps_the_order(self):
        order = self.make_order([(self.lead_product, 1)], status="confirmed", user_id=self.sales.id)

        with self.assertRaises(UserError):
            order.with_user(self.portal).action_request_cancellation("  ")
        request = order.with_user(self.portal).action_request_cancellation("The sample changed")
        task = self.env[MODEL_TASK].search([("document_model", "=", request._name), ("document_id", "=", request.id)])
        with self.assertRaises(UserError):
            order.with_user(self.portal).action_request_cancellation("Again")
        with self.assertRaises(UserError):
            request.with_user(self.sales).action_decline()
        request.with_user(self.sales).reply = "The samples have arrived."
        request.with_user(self.sales).action_decline()

        self.assertEqual(task.assignee_id, self.sales_person)
        self.assertEqual(order.order_status, "confirmed")
        self.assertEqual(request.status, "declined")
        self.assertEqual(request.reply, "The samples have arrived.")
        self.assertEqual(task.status, "done")

    def test_accepting_cancels_the_order_and_does_not_refund(self):
        order = self.make_order([(self.lead_product, 1)], status="confirmed", user_id=self.sales.id)
        request = order.with_user(self.portal).action_request_cancellation("We no longer need it")
        refunds = self.env["account.move"].search_count([("move_type", "=", "out_refund")])

        request.with_user(self.sales).action_accept()

        self.assertEqual(order.order_status, "cancelled")
        self.assertEqual(order.state, "cancel")
        self.assertEqual(request.status, "accepted")
        self.assertEqual(self.env["account.move"].search_count([("move_type", "=", "out_refund")]), refunds)

    def test_customer_can_withdraw_an_open_request(self):
        order = self.make_order([(self.lead_product, 1)], status="confirmed", user_id=self.sales.id)
        request = order.with_user(self.portal).action_request_cancellation("Wait")

        request.with_user(self.portal).action_withdraw()

        self.assertEqual(request.status, "withdrawn")
        self.assertEqual(order.order_status, "confirmed")
        self.assertFalse(order.open_cancellation_request())

    def test_sales_decides_alone_until_the_samples_are_collected(self):
        waiting = self.make_confirmed_order()
        collected = self.make_confirmed_order()
        collected.test_request_id.sample_ids[:1].sudo().received_at = fields.Datetime.now()
        request = collected.with_user(self.portal).action_request_cancellation("Please cancel")

        with self.assertRaisesRegex(UserError, "change request"):
            request.with_user(self.sales).action_accept()
        with self.assertRaisesRegex(UserError, "change request"):
            collected.with_user(self.sales).action_sales_cancel()
        waiting.with_user(self.sales).action_sales_cancel()

        self.assertEqual(collected.order_status, "confirmed")
        self.assertEqual(request.status, "requested")
        self.assertEqual(waiting.order_status, "cancelled")

    def test_sales_can_cancel_a_confirmed_order_that_testing_has_not_finished(self):
        order = self.make_order([(self.lead_product, 1)], status="confirmed", user_id=self.sales.id)

        order.with_user(self.sales).action_sales_cancel()

        self.assertEqual(order.order_status, "cancelled")
        self.assertEqual(order.state, "cancel")
