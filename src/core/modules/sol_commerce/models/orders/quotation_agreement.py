from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_QUOTATION_AGREEMENT, MODEL_SALE_ORDER

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_quotation_agreement as QuotationAgreementBase
else:
    QuotationAgreementBase = object


# Ghi nhận chấp thuận báo giá
class QuotationAgreement(models.TransientModel, QuotationAgreementBase):
    _name = MODEL_QUOTATION_AGREEMENT
    _description = "Record Quotation Agreement"

    if not TYPE_CHECKING:
        # Order whose revised quotation the customer agreed to.
        order_id = fields.Many2one(MODEL_SALE_ORDER, required=True, readonly=True)
        # Reference of the customer's email or written agreement.
        reference = fields.Char(required=True)

    def action_record(self):
        self.ensure_one()
        self.order_id.action_record_quotation_agreement(self.reference)
        return {"type": "ir.actions.act_window_close"}
