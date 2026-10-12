from odoo import api, fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_PAYMENT_PROVIDER


# Cổng thanh toán
class PaymentProvider(models.Model):
    _inherit = MODEL_PAYMENT_PROVIDER

    code = fields.Selection(selection_add=[("payos", "PayOS")], ondelete={"payos": "set default"})

    def _compute_feature_support_fields(self):
        super()._compute_feature_support_fields()
        # PayOS takes the customer to its own page. Refunds are a later feature.
        self.filtered(lambda provider: provider.code == "payos").update(
            {"support_refund": "none", "support_tokenization": False}
        )

    def _get_default_payment_method_codes(self):
        self.ensure_one()
        if self.code != "payos":
            return super()._get_default_payment_method_codes()
        return {"qr"}

    @api.model
    def _find_available_providers(self, company_id, partner_id, amount, **kwargs):
        providers = super()._find_available_providers(company_id, partner_id, amount, **kwargs)
        method = self.env.ref("sol_commerce.payment_method_payos_qr", raise_if_not_found=False)
        if not method or not method.active:
            providers = providers.filtered(lambda provider: provider.code != "payos")
        return providers
