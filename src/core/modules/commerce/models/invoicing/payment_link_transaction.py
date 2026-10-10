import pytz

from odoo import api, fields, models

from odoo.addons.commerce.constants.models import (
    MODEL_INVOICE,
    MODEL_PAYMENT_LINK,
    MODEL_PAYMENT_LINK_TRANSACTION,
    MODEL_VND_MIXIN,
)
from odoo.addons.commerce.constants.payos import PAYOS_TIMEZONE
from odoo.addons.laboratory.constants.models import MODEL_PERMISSION_MIXIN


# Giao Dịch Liên Kết Thanh Toán
class PaymentLinkTransaction(models.Model):
    _name = MODEL_PAYMENT_LINK_TRANSACTION
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_VND_MIXIN]
    _description = "Payment Link Transaction"
    _order = "transacted_at desc, id desc"
    # PayOS reports the transfers; nobody creates or changes them by hand.
    _permission_actions = ("read",)

    # The payment link the transfer paid.
    link_id = fields.Many2one(MODEL_PAYMENT_LINK, string="Payment link", required=True, ondelete="restrict", index=True)
    # The invoice the link pays; kept on the link.
    invoice_id = fields.Many2one(MODEL_INVOICE, related="link_id.invoice_id")
    # The bank reference PayOS sends for the transfer; unique, so a repeated notification is recognised.
    reference = fields.Char(required=True, readonly=True)
    # Amount transferred.
    amount = fields.Monetary(required=True, readonly=True)
    # When the transfer was made, in UTC; PayOS reports it in Vietnam time.
    transacted_at = fields.Datetime(required=True, readonly=True)
    # The Vietnam day of the transfer; reconciliation groups transfers by it.
    transacted_date = fields.Date(compute="_compute_transacted_date", store=True, index=True)

    _reference_unique = models.Constraint("UNIQUE(reference)", "This PayOS transaction is already stored.")

    @api.depends("transacted_at")
    def _compute_transacted_date(self):
        timezone = pytz.timezone(PAYOS_TIMEZONE)
        for transaction in self:
            at = transaction.transacted_at
            transaction.transacted_date = pytz.utc.localize(at).astimezone(timezone).date() if at else False

    @api.depends("reference")
    def _compute_display_name(self):
        for transaction in self:
            transaction.display_name = transaction.reference
