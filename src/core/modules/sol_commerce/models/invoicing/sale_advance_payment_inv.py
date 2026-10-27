from odoo import models

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ADVANCE_PAYMENT_INV
from odoo.addons.sol_commerce.models.invoicing.account_move import BILLING_GROUP


# Tạo Hóa Đơn: Odoo's dialog that creates invoices from orders.
class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = MODEL_SALE_ADVANCE_PAYMENT_INV

    def create_invoices(self):
        """Let a holder of the order's invoice permission create the invoices, which only the accountant posts. Odoo
        opens the new invoices on screens only the accountant reads, so sales goes back to the order."""
        if self.env.su or self.env.user.has_group(BILLING_GROUP):
            return super().create_invoices()
        self.sale_order_ids._check_permission("invoice")
        super(SaleAdvancePaymentInv, self.sudo()).create_invoices()
        return {"type": "ir.actions.act_window_close"}

    def _create_invoices(self, sale_orders):
        """Mark the invoices as the final or advance invoices of their order, as MediLab's own invoicing does."""
        invoices = super()._create_invoices(sale_orders)
        kind = "final" if self.advance_payment_method == "delivered" else "advance"
        for invoice in invoices:
            orders = invoice.line_ids.sale_line_ids.order_id
            invoice.write({"invoice_kind": kind, "order_id": orders.id if len(orders) == 1 else False})
        return invoices
