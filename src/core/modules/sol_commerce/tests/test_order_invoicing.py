from odoo.exceptions import AccessError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ADVANCE_PAYMENT_INV


@tagged("post_install", "-at_install")
class TestOrderInvoicing(OrderCase):
    """Sales with the order's invoice permission create invoices from a confirmed order; the accountant posts them."""

    def make_invoice(self, order, user):
        dialog = (
            self.env[MODEL_SALE_ADVANCE_PAYMENT_INV]
            .with_user(user)
            .with_context(active_model="sale.order", active_ids=order.ids)
            .create({"advance_payment_method": "percentage", "amount": 10})
        )
        return dialog.create_invoices()

    def test_a_holder_of_the_invoice_permission_creates_a_draft_invoice(self):
        order = self.make_confirmed_order()
        before = order.sudo().invoice_ids
        self.sales_person.permission_ids |= self.env.ref("sol_commerce.permission_order_invoice_all")

        self.make_invoice(order, self.sales)

        created = order.sudo().invoice_ids - before
        self.assertEqual(len(created), 1)
        self.assertEqual(created.state, "draft")
        self.assertEqual((created.invoice_kind, created.order_id), ("advance", order))

    def test_sales_without_the_invoice_permission_cannot_create_invoices(self):
        order = self.make_confirmed_order()
        before = order.sudo().invoice_ids

        with self.assertRaises(AccessError):
            self.make_invoice(order, self.sales)

        self.assertEqual(order.sudo().invoice_ids, before)
