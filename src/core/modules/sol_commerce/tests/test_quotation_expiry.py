from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_QUOTATION


@tagged("post_install", "-at_install")
class TestQuotationExpiry(OrderCase):
    def sent_order(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        return order

    def test_expired_quotation_does_not_cancel_the_order(self):
        order = self.sent_order()
        order.payment_deadline = fields.Datetime.now() - timedelta(days=1)

        self.env[MODEL_QUOTATION]._flag_expired()

        self.assertEqual(order._latest_quotation().status, "expired")
        self.assertEqual(order.quotation_follow_up, "expired")
        self.assertEqual(order.order_status, "claimed")
        self.assertNotEqual(order.state, "cancel")

    def test_quotation_before_its_deadline_stays_sent(self):
        order = self.sent_order()

        self.env[MODEL_QUOTATION]._flag_expired()

        self.assertEqual(order._latest_quotation().status, "sent")

    def test_extending_the_deadline_clears_expired(self):
        order = self.sent_order()
        order.payment_deadline = fields.Datetime.now() - timedelta(days=1)
        self.env[MODEL_QUOTATION]._flag_expired()

        order.payment_deadline = fields.Datetime.now() + timedelta(days=2)

        self.assertEqual(order._latest_quotation().status, "sent")
        self.assertEqual(order.quotation_follow_up, "unpaid")
        self.assertEqual(order.order_status, "claimed")

    def test_moving_the_deadline_back_does_not_expire_by_itself(self):
        order = self.sent_order()

        order.payment_deadline = fields.Datetime.now() - timedelta(days=1)

        self.assertEqual(order._latest_quotation().status, "sent")

    def test_expired_quotation_is_sent_again_as_a_new_revision(self):
        order = self.sent_order()
        first = order._latest_quotation()
        order.payment_deadline = fields.Datetime.now() - timedelta(days=1)
        self.env[MODEL_QUOTATION]._flag_expired()

        order.with_user(self.sales).action_send_quotation()

        self.assertEqual(first.status, "replaced")
        self.assertEqual(order._latest_quotation().status, "sent")
        self.assertGreater(order.payment_deadline, fields.Datetime.now())
