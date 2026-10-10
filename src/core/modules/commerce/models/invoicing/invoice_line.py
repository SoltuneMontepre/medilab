from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.commerce.constants.models import MODEL_INVOICE, MODEL_INVOICE_LINE, MODEL_VND_MIXIN
from odoo.addons.laboratory.constants.models import MODEL_PERMISSION_MIXIN


# Dòng Hóa Đơn
class InvoiceLine(models.Model):
    _name = MODEL_INVOICE_LINE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_VND_MIXIN]
    _description = "Invoice Line"
    _order = "sequence, id"

    # The invoice.
    invoice_id = fields.Many2one(MODEL_INVOICE, required=True, ondelete="cascade", index=True)
    # Position of the line on the invoice.
    sequence = fields.Integer(default=10)
    # Text printed on the line, in the customer's language.
    description = fields.Char(required=True)
    # line, advance or advance_deduction.
    kind = fields.Selection(
        [("line", "Line"), ("advance", "Advance"), ("advance_deduction", "Advance Deduction")],
        required=True,
        default="line",
    )
    # Amount excluding VAT; negative for a deduction or an adjustment that lowers the amount.
    amount_untaxed = fields.Monetary(required=True)
    # Tax rate in percent, copied from the quotation line.
    tax_rate = fields.Float(digits=(5, 2), required=True)
    # VAT of the line, rounded by the currency; the invoice totals add up these rounded amounts.
    amount_tax = fields.Monetary(compute="_compute_amount_tax", store=True)
    # Status of the invoice, so the screens lock the lines once it is posted.
    invoice_status = fields.Selection(related="invoice_id.status")

    @api.depends("amount_untaxed", "tax_rate", "currency_id")
    def _compute_amount_tax(self):
        for line in self:
            line.amount_tax = line.currency_id.round(line.amount_untaxed * line.tax_rate / 100)

    @api.constrains("tax_rate", "amount_untaxed", "kind", "invoice_id")
    def _check_amounts(self):
        for line in self:
            if line.tax_rate < 0:
                raise ValidationError(self.env._("A tax rate cannot be negative."))
            negative = line.currency_id.compare_amounts(line.amount_untaxed, 0) < 0
            if line.kind == "advance_deduction" and not negative and not line.currency_id.is_zero(line.amount_untaxed):
                raise ValidationError(self.env._("An advance deduction lowers the invoice: its amount is negative."))
            if line.kind != "advance_deduction" and negative and line.invoice_id.kind != "adjustment":
                raise ValidationError(
                    self.env._("Only an adjustment invoice or an advance deduction has a negative amount.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        invoices = self.env[MODEL_INVOICE].browse({vals["invoice_id"] for vals in vals_list if vals.get("invoice_id")})
        invoices._check_lines_editable()
        return super().create(vals_list)

    def write(self, vals):
        self.invoice_id._check_lines_editable()
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_frozen(self):
        self.invoice_id._check_lines_editable()
