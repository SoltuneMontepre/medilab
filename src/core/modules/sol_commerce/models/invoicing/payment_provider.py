from odoo import api, fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_PAYMENT_PROVIDER
from odoo.addons.sol_laboratory.constants.audit import MASK_SECRET
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN


# Cổng thanh toán
class PaymentProvider(models.Model):
    _name = MODEL_PAYMENT_PROVIDER
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_PAYMENT_PROVIDER]

    code = fields.Selection(selection_add=[("payos", "PayOS")], ondelete={"payos": "set default"})

    def _compute_feature_support_fields(self):
        result = super()._compute_feature_support_fields()
        # PayOS takes the customer to its own page. Refunds are a later feature.
        self.filtered(lambda provider: provider.code == "payos").update(
            {"support_refund": "none", "support_tokenization": False}
        )
        return result

    def _get_default_payment_method_codes(self):
        self.ensure_one()
        if self.code != "payos":
            return super()._get_default_payment_method_codes()
        return {"qr"}

    def _audit_mask(self, field_name):
        # The credentials of a provider are shown only to administrators.
        if self._fields[field_name].groups:
            return MASK_SECRET
        return super()._audit_mask(field_name)

    def unlink(self):
        # Odoo refuses to delete a provider that still has an external id. Drop it before the check.
        if self.ids and self.env.context.get("force_delete"):
            self.env.cr.execute(
                "DELETE FROM ir_model_data WHERE model = %s AND res_id = ANY(%s)",
                (self._name, list(self.ids)),
            )
            self.env.invalidate_all()
        return super().unlink()

    @api.model
    def _find_available_providers(self, company_id, partner_id, amount, **kwargs):
        # Portal users have no access to the provider. The result is only the published PayOS provider.
        public = not self.env.su and not self.env.user._is_internal()
        providers = super(PaymentProvider, self.sudo())._find_available_providers(
            company_id, partner_id, amount, **kwargs
        )
        if public:
            providers = providers.filtered("is_published")
        method = self.sudo().env.ref("sol_commerce.payment_method_payos_qr", raise_if_not_found=False)
        if not method or not method.active:
            providers = providers.filtered(lambda provider: provider.code != "payos")
        if public:
            providers = providers.filtered(lambda provider: provider.code == "payos")
        return providers
