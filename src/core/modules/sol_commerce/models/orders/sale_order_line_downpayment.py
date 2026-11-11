from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_MOVE, MODEL_SALE_ORDER_LINE

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order_line as SaleOrderLineBase
else:
    SaleOrderLineBase = object


# Dòng Đơn Hàng: a down payment line leads to the advance invoice that billed it.
class SaleOrderLine(models.Model, SaleOrderLineBase):
    _inherit = MODEL_SALE_ORDER_LINE

    if not TYPE_CHECKING:
        # The customer invoice that billed the down payment; empty on other lines and before it is invoiced.
        downpayment_invoice_id = fields.Many2one(
            MODEL_ACCOUNT_MOVE, string="Invoice", compute="_compute_downpayment_invoice_id", compute_sudo=True
        )

    @api.depends("is_downpayment", "invoice_lines.move_id.state")
    def _compute_downpayment_invoice_id(self):
        for line in self:
            invoices = line.invoice_lines.move_id.filtered(
                lambda move: move.move_type == "out_invoice" and move.state != "cancel"
            )
            line.downpayment_invoice_id = invoices[-1:] if line.is_downpayment else False
