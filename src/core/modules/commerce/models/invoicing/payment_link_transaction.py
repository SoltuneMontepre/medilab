import pytz

from odoo import api, fields, models

from odoo.addons.commerce.constants.models import (
    MODEL_INVOICE,
    MODEL_PAYMENT,
    MODEL_PAYMENT_LINK,
    MODEL_PAYMENT_LINK_TRANSACTION,
    MODEL_RECONCILIATION_DAY,
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
    # The online payment that records the transfer; empty until it is recorded.
    payment_id = fields.Many2one(MODEL_PAYMENT, readonly=True, ondelete="restrict", index=True)
    # The reconciliation day of the transfer's Vietnam day, once the accountant opens it.
    day_id = fields.Many2one(
        MODEL_RECONCILIATION_DAY,
        string="Reconciliation day",
        compute="_compute_day_id",
        store=True,
        ondelete="set null",
    )
    # missing_payment, underpaid, overpaying or matched: how the row reconciles.
    match_state = fields.Selection(
        [
            ("missing_payment", "Missing payment"),
            ("underpaid", "Underpaid link"),
            ("overpaying", "Overpaying"),
            ("matched", "Matched"),
        ],
        compute="_compute_match_state",
    )
    # True while an underpaid link or an overpaying payment of the row lacks its acknowledgement.
    needs_acknowledgement = fields.Boolean(compute="_compute_match_state")
    # True when the payment was recorded after the day was locked (a late PayOS confirmation).
    recorded_after_lock = fields.Boolean(related="payment_id.recorded_after_lock")

    _reference_unique = models.Constraint("UNIQUE(reference)", "This PayOS transaction is already stored.")
    _payment_unique = models.Constraint("UNIQUE(payment_id)", "This payment already records another transaction.")

    @api.depends("transacted_at")
    def _compute_transacted_date(self):
        timezone = pytz.timezone(PAYOS_TIMEZONE)
        for transaction in self:
            at = transaction.transacted_at
            transaction.transacted_date = pytz.utc.localize(at).astimezone(timezone).date() if at else False

    @api.depends("transacted_date")
    def _compute_day_id(self):
        days = self.env[MODEL_RECONCILIATION_DAY].sudo()
        for transaction in self:
            transaction.day_id = days.search([("day", "=", transaction.transacted_date)], limit=1)

    @api.depends(
        "payment_id",
        "payment_id.is_overpaying",
        "payment_id.acknowledged_at",
        "link_id.match_status",
        "link_id.is_acknowledged",
    )
    def _compute_match_state(self):
        for transaction in self:
            payment, link = transaction.payment_id, transaction.link_id
            if not payment:
                state, pending = "missing_payment", False
            elif payment.is_overpaying:
                state, pending = "overpaying", not payment.acknowledged_at
            elif link.match_status == "underpaid":
                state, pending = "underpaid", not link.is_acknowledged
            else:
                state, pending = "matched", False
            transaction.match_state = state
            transaction.needs_acknowledgement = pending

    @api.depends("reference")
    def _compute_display_name(self):
        for transaction in self:
            transaction.display_name = transaction.reference

    def write(self, vals):
        # Joining a day that is opened later is bookkeeping, not a change of what PayOS reported.
        if set(vals) - {"day_id"}:
            self._check_unlocked_day()
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_locked(self):
        self._check_unlocked_day()

    def _check_unlocked_day(self):
        self.env[MODEL_RECONCILIATION_DAY]._check_unlocked(
            self.mapped("transacted_date"), self.env._("A PayOS transaction")
        )

    def action_record_payments(self):
        # Row button of the reconciliation day: records the missing payments of the row's link.
        self.link_id.action_record_payments()

    def action_acknowledge(self):
        # Row button of the reconciliation day: the acknowledgement lives on the link or on the payment.
        self.ensure_one()
        if self.match_state == "overpaying":
            return self.payment_id.action_acknowledge()
        return self.link_id.action_acknowledge()
