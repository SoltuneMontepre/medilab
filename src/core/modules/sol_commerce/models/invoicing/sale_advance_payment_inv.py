from typing import TYPE_CHECKING

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ADVANCE_PAYMENT_INV
from odoo.addons.sol_commerce.constants.orders import STATUS_CONFIRMED
from odoo.addons.sol_commerce.models.invoicing.account_move import BILLING_GROUP

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_advance_payment_inv as SaleAdvancePaymentInvBase
else:
    SaleAdvancePaymentInvBase = object


# Tạo Hóa Đơn: Odoo's dialog that creates invoices from orders.
class SaleAdvancePaymentInv(models.TransientModel, SaleAdvancePaymentInvBase):
    _inherit = MODEL_SALE_ADVANCE_PAYMENT_INV

    def create_invoices(self):
        """Let a holder of the order's invoice permission create the invoices of confirmed orders, which only the
        accountant posts. Odoo opens the new invoices on screens only the accountant reads, so sales goes back to the
        order."""
        if self.env.su or self.env.user.has_group(BILLING_GROUP):
            return super().create_invoices()
        self.sale_order_ids._check_permission("invoice")
        if any(order.order_status != STATUS_CONFIRMED for order in self.sale_order_ids):
            raise UserError(self.env._("Invoices are created only from confirmed orders."))
        super(SaleAdvancePaymentInv, self.sudo()).create_invoices()
        return {"type": "ir.actions.act_window_close"}

    def _create_invoices(self, sale_orders):
        """Create one invoice per order and mark it as the final or advance invoice of that order, as MediLab's own
        invoicing does."""
        self.consolidated_billing = False
        invoices = super()._create_invoices(sale_orders)
        kind = "final" if self.advance_payment_method == "delivered" else "advance"
        for invoice in invoices:
            invoice.write({"invoice_kind": kind, "order_id": invoice.line_ids.sale_line_ids.order_id.id})
        return invoices
