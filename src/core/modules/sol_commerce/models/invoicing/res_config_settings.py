from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS

PAYOS_EXPIRY_PARAMETER = "sol_commerce.payos_expiry_hours"
DEFAULT_PAYOS_EXPIRY_HOURS = 24


# Cài Đặt
class ResConfigSettings(models.TransientModel):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    # PayOS is offered on the portal when this is on.
    payos_enabled = fields.Boolean(string="PayOS")
    # The QR method is offered only when PayOS and this are both on.
    payos_qr_enabled = fields.Boolean(string="PayOS QR")
    # Hours before a PayOS link expires. A payment PayOS confirms after that still counts.
    payos_expiry_hours = fields.Integer(
        string="PayOS link expiry (hours)",
        config_parameter=PAYOS_EXPIRY_PARAMETER,
        default=DEFAULT_PAYOS_EXPIRY_HOURS,
    )

    def get_values(self):
        values = super().get_values()
        provider = self.env.ref("sol_commerce.payment_provider_payos", raise_if_not_found=False)
        method = self.env.ref("sol_commerce.payment_method_payos_qr", raise_if_not_found=False)
        values.update(
            payos_enabled=bool(provider and provider.is_published),
            payos_qr_enabled=bool(method and method.active),
        )
        return values

    def set_values(self):
        super().set_values()
        provider = self.env.ref("sol_commerce.payment_provider_payos", raise_if_not_found=False)
        method = self.env.ref("sol_commerce.payment_method_payos_qr", raise_if_not_found=False)
        if provider:
            provider.is_published = self.payos_enabled
        if method:
            method.active = self.payos_qr_enabled and self.payos_enabled
