from odoo.exceptions import UserError
from odoo.tests import tagged

from .order_case import OrderCase


@tagged("post_install", "-at_install")
class TestQuotationDecline(OrderCase):
    def sent_quotation(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        return order, order._latest_quotation()

    def test_declining_stores_the_reason_and_tells_the_salesperson(self):
        order, quotation = self.sent_quotation()
        status = order.order_status

        quotation.action_decline("Too expensive")

        self.assertEqual(quotation.status, "declined")
        self.assertEqual(quotation.decline_reason, "Too expensive")
        self.assertEqual(order.order_status, status)
        self.assertEqual(order.quotation_follow_up, "declined")
        messages = order.message_ids.filtered(lambda message: "Too expensive" in (message.body or ""))
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages.partner_ids, self.sales.partner_id)

    def test_declining_needs_a_reason(self):
        _order, quotation = self.sent_quotation()

        with self.assertRaises(UserError):
            quotation.action_decline("  ")

        self.assertEqual(quotation.status, "sent")

    def test_only_a_sent_quotation_can_be_declined(self):
        _order, quotation = self.sent_quotation()
        quotation.action_decline("No budget")

        with self.assertRaises(UserError):
            quotation.action_decline("Again")

    def test_a_declined_quotation_can_be_sent_as_a_new_revision(self):
        order, quotation = self.sent_quotation()
        quotation.action_decline("Too expensive")

        order.with_user(self.sales).action_send_quotation()

        self.assertEqual(quotation.status, "replaced")
        self.assertEqual(order.quotation_follow_up, "unpaid")
