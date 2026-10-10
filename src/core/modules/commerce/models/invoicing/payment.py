import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain
from odoo.tools import format_list

from odoo.addons.commerce.constants.models import (
    MODEL_INVOICE,
    MODEL_PAYMENT,
    MODEL_PAYMENT_LINK,
    MODEL_PAYMENT_LINK_TRANSACTION,
    MODEL_RECONCILIATION_DAY,
    MODEL_VND_MIXIN,
)
from odoo.addons.commerce.constants.sequences import SEQUENCE_RECEIPT
from odoo.addons.commerce.constants.xml_ids import REPORT_RECEIPT
from odoo.addons.commerce.models.invoicing.payment_link import OPEN_STATUSES, PROVIDER_UPDATE_KEY
from odoo.addons.laboratory.constants.models import MODEL_ARCHIVE_MIXIN, MODEL_IR_SEQUENCE, MODEL_PERMISSION_MIXIN

_logger = logging.getLogger(__name__)

# What a payment is once it is confirmed or rejected; everything else about it stays as recorded.
FROZEN_FIELDS = {"invoice_id", "amount", "payment_date", "method", "payment_link_id"}
MANUAL_METHODS = ("bank_transfer", "cash")


# Thanh Toán
class Payment(models.Model):
    _name = MODEL_PAYMENT
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_VND_MIXIN]
    _description = "Payment"
    _order = "payment_date desc, id desc"

    # The invoice paid.
    invoice_id = fields.Many2one(MODEL_INVOICE, required=True, ondelete="restrict", index=True)
    # The customer billed; kept on the invoice.
    partner_id = fields.Many2one(related="invoice_id.partner_id")
    # Amount paid.
    amount = fields.Monetary(required=True)
    # Date the money was received.
    payment_date = fields.Date(required=True, default=fields.Date.context_today)
    # online, bank_transfer or cash; online payments come only from PayOS transactions.
    method = fields.Selection(
        [("online", "Online"), ("bank_transfer", "Bank transfer"), ("cash", "Cash")],
        required=True,
        default="bank_transfer",
    )
    # pending, confirmed or rejected; only confirmed payments count.
    status = fields.Selection(
        [("pending", "Pending"), ("confirmed", "Confirmed"), ("rejected", "Rejected")],
        required=True,
        default="pending",
        index=True,
        copy=False,
    )
    # The user who recorded the payment; empty for an online payment.
    recorded_by_id = fields.Many2one("res.users", string="Recorded by", readonly=True, ondelete="restrict")
    # The accountant who confirmed or rejected it.
    reviewed_by_id = fields.Many2one("res.users", string="Reviewed by", readonly=True, ondelete="restrict")
    # When it was confirmed or rejected.
    reviewed_at = fields.Datetime(readonly=True)
    # The accountant's reason for rejecting it.
    rejection_reason = fields.Text()
    # Unique receipt number, from the sequence medilab.payment.receipt when the payment is confirmed.
    receipt_code = fields.Char(readonly=True, copy=False, index=True)
    # The receipt's PDF, stored at confirmation.
    receipt_attachment_id = fields.Many2one("ir.attachment", readonly=True, copy=False, ondelete="set null")
    # The payment link the online payment came from; empty for a manual payment.
    payment_link_id = fields.Many2one(MODEL_PAYMENT_LINK, string="Payment link", ondelete="restrict", index=True)
    # The PayOS transfer the online payment records; one row.
    transaction_ids = fields.One2many(MODEL_PAYMENT_LINK_TRANSACTION, "payment_id", string="Transaction")
    # True when this payment took the invoice's owed amount below zero; decided once, when it was recorded.
    is_overpaying = fields.Boolean(readonly=True)
    # The accountant who acknowledged the overpayment before locking its day.
    acknowledged_by_id = fields.Many2one("res.users", string="Acknowledged by", readonly=True, ondelete="restrict")
    # When the overpayment was acknowledged.
    acknowledged_at = fields.Datetime(readonly=True)
    # Why the overpayment is accepted as it is.
    acknowledgement_reason = fields.Text()
    # True when the online payment was recorded after its reconciliation day was locked (a late PayOS
    # confirmation); decided once, when it was recorded.
    recorded_after_lock = fields.Boolean(readonly=True)
    # True when the payment's reconciliation day is locked.
    is_day_locked = fields.Boolean(compute="_compute_is_day_locked")

    _amount_positive = models.Constraint("CHECK(amount > 0)", "A payment has a positive amount.")
    _receipt_unique = models.Constraint("UNIQUE(receipt_code)", "A receipt with this number already exists.")

    def _compute_is_day_locked(self):
        locked = self.env[MODEL_RECONCILIATION_DAY]._locked_days(self.mapped("payment_date"))
        for payment in self:
            payment.is_day_locked = payment.method == "online" and payment.payment_date in locked

    @api.depends("receipt_code", "invoice_id.code", "status")
    def _compute_display_name(self):
        for payment in self:
            payment.display_name = payment.receipt_code or self.env._(
                "%(status)s payment on %(invoice)s",
                status=dict(self._fields["status"]._description_selection(self.env))[payment.status],
                invoice=payment.invoice_id.display_name,
            )

    @api.model_create_multi
    def create(self, vals_list):
        provider = self.env.su or self.env.context.get(PROVIDER_UPDATE_KEY)
        confirm_now = []
        for vals in vals_list:
            online = vals.get("method") == "online"
            if online and not provider:
                raise UserError(self.env._("An online payment is recorded from a PayOS transaction, never by hand."))
            if not online:
                vals.setdefault("recorded_by_id", self.env.user.id)
            elif vals.get("payment_date") and "recorded_after_lock" not in vals:
                locked = self.env[MODEL_RECONCILIATION_DAY]._locked_days([fields.Date.to_date(vals["payment_date"])])
                vals["recorded_after_lock"] = bool(locked)
            # A creator who may confirm payments records them confirmed; a status given explicitly (data) is kept.
            confirm_now.append("status" not in vals and (online or self._has_permission("edit")))
        payments = super().create(vals_list)
        payments._check_recordable()
        for payment, confirm in zip(payments, confirm_now, strict=True):
            if confirm:
                payment._confirm()
            elif payment.method != "online":
                payment._check_owed()
        return payments

    def write(self, vals):
        self._check_unlocked_day()
        reviewed = self.filtered(lambda payment: payment.status != "pending")
        if reviewed and set(vals) & FROZEN_FIELDS:
            raise UserError(
                self.env._(
                    "%s cannot be changed once confirmed or rejected.",
                    format_list(self.env, reviewed.mapped("display_name")),
                )
            )
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_reviewed(self):
        reviewed = self.filtered(lambda payment: payment.status != "pending")
        if reviewed:
            raise UserError(
                self.env._(
                    "Only a pending payment can be deleted: %s", format_list(self.env, reviewed.mapped("display_name"))
                )
            )

    def _in_use_domain(self):
        return Domain("status", "=", "pending")

    def _check_recordable(self):
        for payment in self:
            invoice = payment.invoice_id
            if invoice.status != "posted" or invoice.kind == "adjustment":
                raise UserError(
                    self.env._(
                        "A payment is recorded on a posted advance or final invoice, not on %s.", invoice.display_name
                    )
                )

    def _check_owed(self):
        # The owed amount is read fresh, so a payment confirmed meanwhile is counted; a payment already counted
        # (confirmed data) is not held against itself.
        for payment in self.filtered(lambda payment: payment.method != "online"):
            invoice = payment.invoice_id
            invoice.invalidate_recordset()
            owed = invoice.amount_owed + (payment.amount if payment.status == "confirmed" else 0)
            if invoice.currency_id.compare_amounts(payment.amount, owed) > 0:
                raise UserError(
                    self.env._(
                        "The payment of %(amount)s exceeds the %(owed)s still owed on %(invoice)s.",
                        amount=invoice.currency_id.format(payment.amount),
                        owed=invoice.currency_id.format(owed),
                        invoice=invoice.display_name,
                    )
                )

    def _check_unlocked_day(self):
        online = self.filtered(lambda payment: payment.method == "online")
        if online:
            self.env[MODEL_RECONCILIATION_DAY]._check_unlocked(
                online.mapped("payment_date"), self.env._("An online payment")
            )

    def action_confirm(self):
        self._check_permission("edit")
        if any(payment.status != "pending" for payment in self):
            raise UserError(self.env._("Only a pending payment can be confirmed."))
        self._confirm()

    def _confirm(self):
        """Count the payment: under the invoice row lock, check the owed amount, number the receipt and store it."""
        for payment in self:
            invoice = payment.invoice_id
            invoice._lock()
            invoice.invalidate_recordset()
            if payment.method != "online":
                payment._check_owed()
            owed_before = invoice.amount_owed
            payment.write(
                {
                    "status": "confirmed",
                    "reviewed_by_id": False if payment.method == "online" else self.env.user.id,
                    "reviewed_at": fields.Datetime.now(),
                    "receipt_code": payment.receipt_code or self._next_receipt_code(),
                    "is_overpaying": invoice.currency_id.compare_amounts(owed_before - payment.amount, 0) < 0,
                }
            )
            payment._store_receipt()
            invoice.invalidate_recordset()
            if invoice.currency_id.compare_amounts(invoice.amount_owed, 0) <= 0:
                payment._queue_cancellations()

    @api.model
    def _next_receipt_code(self):
        return self.env[MODEL_IR_SEQUENCE].next_by_code(SEQUENCE_RECEIPT, sequence_date=fields.Date.context_today(self))

    def _queue_cancellations(self):
        # The invoice is settled: its other open links are cancelled by the job, never by a call under the lock.
        self.ensure_one()
        links = self.invoice_id.payment_link_ids.filtered(lambda link: link.status in OPEN_STATUSES)
        for link in links - self.payment_link_id:
            link._queue_call("cancel")

    def _store_receipt(self):
        self.ensure_one()
        content, report_type = self.env["ir.actions.report"].sudo()._render_qweb_pdf(REPORT_RECEIPT, self.ids)
        extension, mimetype = ("pdf", "application/pdf") if report_type == "pdf" else ("html", "text/html")
        attachment = (
            self.env["ir.attachment"]
            .sudo()
            .create(
                {
                    "name": f"{self.receipt_code.replace('/', '-')}.{extension}",
                    "type": "binary",
                    "raw": content,
                    "mimetype": mimetype,
                    "res_model": self._name,
                    "res_id": self.id,
                }
            )
        )
        self.write({"receipt_attachment_id": attachment.id})

    def action_reject(self):
        self._check_permission("edit")
        for payment in self:
            if payment.status != "pending":
                raise UserError(self.env._("Only a pending payment can be rejected."))
            if not payment.rejection_reason:
                raise UserError(self.env._("Give the reason for rejecting the payment first."))
            payment.write(
                {"status": "rejected", "reviewed_by_id": self.env.user.id, "reviewed_at": fields.Datetime.now()}
            )
            payment._notify_rejected()

    def _notify_rejected(self):
        # Until notifications exist, the rejection is logged; the notifications feature tells the salesperson.
        _logger.info(
            "Payment on %s recorded by %s rejected: %s",
            self.invoice_id.display_name,
            self.recorded_by_id.login,
            self.rejection_reason,
        )

    def action_print_receipt(self):
        if any(payment.status != "confirmed" for payment in self):
            raise UserError(self.env._("A receipt exists for a confirmed payment only."))
        return self.env.ref(REPORT_RECEIPT).sudo().report_action(self, config=False)

    def action_acknowledge(self):
        """Accept an overpaying payment as it is, so its reconciliation day can be locked."""
        if not self.env[MODEL_RECONCILIATION_DAY]._has_permission("edit"):
            raise AccessError(
                self.env._("Acknowledging a reconciliation row needs the edit permission on reconciliation days.")
            )
        for payment in self:
            if not payment.is_overpaying:
                raise UserError(self.env._("%s is not an overpayment.", payment.display_name))
            if not payment.acknowledgement_reason:
                raise UserError(self.env._("Give the reason for accepting the overpayment first."))
            payment.sudo().write({"acknowledged_by_id": self.env.user.id, "acknowledged_at": fields.Datetime.now()})
