from odoo import api, fields, models

from odoo.addons.commerce.constants.payos import PAYMENT_METHODS
from odoo.addons.commerce.services.payos_client import PayosClient
from odoo.addons.laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS

INVOICE_DUE_DAYS = "invoice_due_days"
PAYOS_ENABLED = "payos_enabled"
PAYOS_LINK_EXPIRY_HOURS = "payos_link_expiry_hours"


# Cấu Hình Hệ Thống
class ResConfigSettings(models.TransientModel):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    # Days a customer has to pay an invoice after it is posted.
    invoice_due_days = fields.Integer(
        config_parameter="medilab.commerce.invoice_due_days",
        default=7,
        help="Days a customer has to pay an invoice after it is posted.",
    )
    # Whether online payments through PayOS are offered.
    payos_enabled = fields.Boolean(
        config_parameter="medilab.commerce.payos_enabled",
        default=False,
        string="PayOS payments",
        help="Take online payments through PayOS. The credentials come from the environment, never from here.",
    )
    # Whether bank transfer by QR code is offered on the payment page.
    payos_method_qr_transfer = fields.Boolean(
        config_parameter="medilab.commerce.payos_method_qr_transfer",
        default=True,
        string="Bank transfer by QR code",
        help="Offer bank transfer by QR code on the payment page.",
    )
    # Hours a payment link stays payable after it is created.
    payos_link_expiry_hours = fields.Integer(
        config_parameter="medilab.commerce.payos_link_expiry_hours",
        default=72,
        help="Hours a payment link stays payable after it is created.",
    )
    # Whether the three PayOS credentials are set in the environment; their values are never shown.
    payos_configured = fields.Boolean(compute="_compute_payos_configured")

    def _compute_payos_configured(self):
        self.payos_configured = PayosClient().is_configured()

    @api.model
    def _enabled_payment_methods(self):
        """The PayOS payment methods the administrator left on; the payment page offers only these."""
        return [method for method, field_name in PAYMENT_METHODS.items() if self._get_parameter(field_name)]
