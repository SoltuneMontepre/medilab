from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_QUOTATION


@tagged("post_install", "-at_install")
class TestAdvanceDueDate(OrderCase):
    def test_request_keeps_the_exact_quotation_deadline(self):
        order = self.make_quotable_order()
        deadline = fields.Datetime.now() + timedelta(days=5, hours=3)
        order.payment_deadline = deadline
        order.with_user(self.sales).action_send_quotation()

        self.assertEqual(order.payment_request_id.deadline, deadline)
        self.assertFalse(order.invoice_ids)

    def test_extending_an_expired_quotation_reopens_the_request(self):
        order = self.sent_order()
        order.payment_deadline = fields.Datetime.now() - timedelta(days=2)
        self.env[MODEL_QUOTATION]._flag_expired()
        self.assertEqual(order.payment_request_id.state, "expired")
        self.assertFalse(order.invoice_ids)

        deadline = fields.Datetime.now() + timedelta(days=3)
        order.with_user(self.sales).payment_deadline = deadline

        self.assertEqual(order._latest_quotation().status, "sent")
        self.assertEqual(order.payment_request_id.state, "open")
        self.assertEqual(order.payment_request_id.deadline, deadline)

    def test_a_paid_advance_keeps_its_due_date(self):
        order = self.sent_order()
        self.pay_advance(order)
        invoice = order.invoice_ids
        due_date = invoice.invoice_date_due

        order.payment_deadline = fields.Datetime.now() + timedelta(days=20)

        self.assertEqual(invoice.invoice_date_due, due_date)
