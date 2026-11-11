from datetime import date, datetime, time, timedelta

from odoo import fields
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_MOVE, MODEL_QUOTATION
from odoo.addons.sol_laboratory.tests.assertions import assert_instance

VIETNAM = "Asia/Ho_Chi_Minh"


@tagged("post_install", "-at_install")
class TestAdvanceDueDate(OrderCase):
    def setUp(self):
        super().setUp()
        self.env.company.tz = VIETNAM

    def send(self, order):
        order.with_user(self.sales).action_send_quotation()
        return order._latest_quotation().sudo().advance_invoice_id

    def overdue(self, invoice):
        return invoice in self.env[MODEL_ACCOUNT_MOVE].sudo().search([("is_overdue", "=", True)])

    def test_the_advance_is_due_on_the_default_payment_deadline(self):
        order = self.make_quotable_order()

        invoice = self.send(order)

        laboratory = order.with_context(tz=VIETNAM)
        deadline = fields.Datetime.context_timestamp(laboratory, assert_instance(order.payment_deadline, datetime))
        self.assertEqual(invoice.invoice_date_due, deadline.date())
        self.assertGreater(assert_instance(invoice.invoice_date_due, date), fields.Date.context_today(laboratory))
        self.assertFalse(invoice.invoice_payment_term_id)
        self.assertFalse(invoice.is_overdue)
        self.assertFalse(self.overdue(invoice))

    def test_the_due_date_is_the_laboratory_day_of_the_deadline(self):
        order = self.make_quotable_order()
        day = date.today() + timedelta(days=5)
        # 18:00 UTC is 01:00 the next day in Vietnam.
        order.payment_deadline = datetime.combine(day, time(18))

        invoice = self.send(order)

        self.assertEqual(invoice.invoice_date_due, day + timedelta(days=1))

    def test_sales_setting_another_deadline_moves_the_due_date(self):
        order = self.make_quotable_order()
        invoice = self.send(order)
        day = date.today() + timedelta(days=10)

        order.with_user(self.sales).payment_deadline = datetime.combine(day, time(3))

        self.assertEqual(invoice.invoice_date_due, day)
        self.assertEqual(invoice.line_ids.filtered("date_maturity").mapped("date_maturity"), [day])

    def test_extending_an_expired_quotation_moves_the_due_date(self):
        order = self.make_quotable_order()
        invoice = self.send(order)
        order.payment_deadline = fields.Datetime.now() - timedelta(days=2)
        self.env[MODEL_QUOTATION]._flag_expired()
        self.assertTrue(self.overdue(invoice))

        order.payment_deadline = fields.Datetime.now() + timedelta(days=3)

        self.assertEqual(order._latest_quotation().status, "sent")
        self.assertGreater(assert_instance(invoice.invoice_date_due, date), date.today())
        self.assertFalse(self.overdue(invoice))

    def test_a_paid_advance_keeps_its_due_date(self):
        order = self.make_quotable_order()
        invoice = self.send(order)
        due_date = invoice.invoice_date_due
        self.pay_advance(order)

        order.payment_deadline = fields.Datetime.now() + timedelta(days=20)

        self.assertEqual(invoice.invoice_date_due, due_date)
