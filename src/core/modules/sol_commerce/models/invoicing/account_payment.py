import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_PAYMENT
from odoo.addons.sol_commerce.constants.notifications import EVENT_PAYMENT_RECEIPT, EVENT_PAYMENT_REJECTED
from odoo.addons.sol_commerce.models.invoicing.account_move import ADMINISTRATOR_GROUP, BILLING_GROUP
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN

_logger = logging.getLogger(__name__)

METHOD_SELECTION = [("online", "Online"), ("bank_transfer", "Bank transfer"), ("cash", "Cash")]
METHODS = {method for method, _label in METHOD_SELECTION}
# States of a payment the accountant or the gateway confirmed; a draft is pending.
CONFIRMED_STATES = ("paid", "reconciled")
JOURNAL_TYPE = {"online": "bank", "bank_transfer": "bank", "cash": "cash"}


# Phiếu thu
class AccountPayment(models.Model):
    # _name is required to add a mixin to an Odoo model. The audit mixin comes first so it wraps Odoo's write.
    _name = MODEL_ACCOUNT_PAYMENT
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_ACCOUNT_PAYMENT]

    # online, bank_transfer or cash.
    method = fields.Selection(METHOD_SELECTION, string="Collection Method")
    # The accountant who confirmed or rejected the payment.
    reviewed_by_id = fields.Many2one("res.users", string="Reviewed By", readonly=True, copy=False)
    # When it was confirmed or rejected.
    reviewed_at = fields.Datetime(readonly=True, copy=False)
    # Why the accountant rejected it.
    rejection_reason = fields.Text(copy=False)
    # The PayOS amount was more than the invoice still owed. The invoice keeps Odoo's payment status.
    exceeds_residual = fields.Boolean(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        payments = super().create(vals_list)
        payments._invalidate_order_pending()
        return payments

    @api.model
    def create_pending_payment(self, invoice, amount, method):
        """Sales records a cash or transfer payment. It stays a draft until the accountant confirms it."""
        if method not in METHODS - {"online"}:
            raise UserError(self.env._("Sales records cash and bank transfers. Online payments come from PayOS."))
        self._lock_invoices(invoice)
        amount = self._validated_collection_amount(invoice, amount)
        return self.create(self._payment_values(invoice, amount, method))

    @api.model
    def _validated_collection_amount(self, invoice, amount):
        """The amount a new payment may collect. An empty amount means the whole residual."""
        if self._amount_omitted(amount):
            amount = invoice.amount_residual
        else:
            try:
                amount = float(amount)
            except (TypeError, ValueError) as error:
                raise UserError(self.env._("Enter an amount greater than zero.")) from error
        currency = invoice.currency_id
        amount = currency.round(amount)
        if currency.compare_amounts(amount, 0) <= 0:
            raise UserError(self.env._("Enter an amount greater than zero."))
        if currency.compare_amounts(amount, invoice.amount_residual) > 0:
            raise UserError(self.env._("A payment cannot be more than the amount still owed."))
        return amount

    @api.model
    def _amount_omitted(self, amount):
        return amount is None or amount is False or (isinstance(amount, str) and not amount)

    def action_post(self):
        if self.filtered("method"):
            self._check_billing()
            self._lock_invoices(self.invoice_ids)
            for payment in self:
                payment._check_collection_amount()
            self.write({"reviewed_by_id": self.env.user.id, "reviewed_at": fields.Datetime.now()})
        posted = super().action_post()
        for payment in self.filtered("method"):
            payment._reconcile_with_invoices()
            payment._queue_customer_notice(EVENT_PAYMENT_RECEIPT, "receipt")
        return posted

    def action_reject_payment(self):
        """Cancel a draft payment and leave the reason as an activity for the salesperson."""
        self.ensure_one()
        self._check_billing()
        reason = self.rejection_reason
        if not reason:
            raise UserError(self.env._("A rejected payment needs a reason."))
        if any(payment.state != "draft" for payment in self):
            raise UserError(self.env._("Only a draft payment can be rejected."))
        self.write(
            {
                "rejection_reason": reason,
                "reviewed_by_id": self.env.user.id,
                "reviewed_at": fields.Datetime.now(),
            }
        )
        invoices = self.invoice_ids
        previous = {invoice.id: invoice.payment_state for invoice in invoices}
        self.action_cancel()
        for invoice in invoices:
            if invoice.payment_state != previous[invoice.id]:
                raise UserError(self.env._("Rejecting a payment must leave the invoice as it was."))
        self._notify_salesperson(reason)
        self._queue_customer_notice(EVENT_PAYMENT_REJECTED, "rejected")
        return True

    def write(self, vals):
        frozen = self.filtered(
            lambda payment: payment.method == "online" and payment.state != "draft" and payment._online_day_locked()
        )
        changed = {"amount", "partner_id", "journal_id", "method", "date"} & set(vals)
        if frozen and (changed or vals.get("state") in {"draft", "canceled", "rejected"}):
            raise UserError(self.env._("An online payment of a locked day cannot be changed."))
        orders = self._orders_for_pending()
        result = super().write(vals)
        (orders | self._orders_for_pending()).invalidate_recordset(["pending_amount"])
        return result

    def _check_collection_amount(self):
        self.ensure_one()
        owed = sum(self.invoice_ids.mapped("amount_residual"))
        if self.method == "online":
            if self.amount > owed:
                self.exceeds_residual = True
            return
        if self.method in ("cash", "bank_transfer") and self.amount > owed:
            raise UserError(self.env._("A payment cannot be more than the amount still owed."))

    def _reconcile_with_invoices(self):
        self.ensure_one()
        if not self.invoice_ids or not self.move_id:
            return
        _liquidity, counterpart, _writeoff = self._seek_for_lines()
        receivable = self.invoice_ids.line_ids.filtered(
            lambda line: line.account_type == "asset_receivable" and not line.reconciled
        )
        lines = counterpart + receivable
        if lines:
            lines.reconcile()

    def _notify_salesperson(self, reason):
        salesperson = self.invoice_ids.invoice_user_id[:1]
        if not salesperson:
            return
        self.env["mail.activity"].sudo().create(
            {
                "res_model_id": self.env["ir.model"]._get(self._name).id,
                "res_id": self.id,
                "user_id": salesperson.id,
                "summary": self.env._("Payment rejected"),
                "note": reason,
                "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
            }
        )

    def _queue_customer_notice(self, code, kind):
        """Queue the customer notice after the payment is saved. A provider outage does not undo it."""
        self.ensure_one()
        partner = self.partner_id
        if not partner:
            return
        body = self.env._("Payment of %(amount)s was recorded.", amount=self.amount)
        if kind == "rejected":
            body = self.env._("Payment was rejected: %(reason)s", reason=self.rejection_reason or "")
        try:
            with self.env.cr.savepoint():
                self.env["mail.message"].raise_event(
                    code,
                    self,
                    f"payment:{self.id}:{kind}",
                    body,
                    partners=partner,
                )
        except Exception:
            _logger.exception("Payment notice was not queued")

    def _online_day_locked(self):
        self.ensure_one()
        days = self.env["medilab.reconciliation.day"]
        moment = self.payment_transaction_id.payos_transferred_at
        if not moment:
            return False
        return days._day_is_locked(days._vietnam_day(moment))

    def _check_billing(self):
        if self.env.su or self.env.user.has_group(BILLING_GROUP) or self.env.user.has_group(ADMINISTRATOR_GROUP):
            return
        raise AccessError(self.env._("Only the accountant can confirm or reject a payment."))

    @api.model
    def _lock_invoices(self, invoices):
        if invoices:
            self.env.cr.execute("SELECT id FROM account_move WHERE id IN %s FOR UPDATE", (tuple(invoices.ids),))

    @api.model
    def _payment_values(self, invoice, amount, method):
        journal = self.env["account.journal"].search(
            [("type", "=", JOURNAL_TYPE[method]), ("company_id", "=", invoice.company_id.id)], limit=1
        )
        if not journal:
            raise UserError(self.env._("The company has no journal for this payment."))
        return {
            "amount": amount,
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": invoice.partner_id.id,
            "currency_id": invoice.currency_id.id,
            "journal_id": journal.id,
            "method": method,
            "invoice_ids": [Command.set(invoice.ids)],
            "memo": invoice.name,
        }

    @api.model
    def portal_pay_invoice(self, invoice, amount=None):
        """The customer pays their own invoice. The amount is checked here, not trusted from the page."""
        self._check_portal_invoice(invoice)
        self._lock_invoices(invoice)
        existing = self.sudo().search(
            [("invoice_ids", "in", invoice.ids), ("method", "=", "bank_transfer"), ("state", "=", "draft")],
            limit=1,
        )
        if existing:
            return existing
        if invoice.amount_residual <= 0:
            raise UserError(self.env._("This invoice is already paid."))
        amount = self._validated_collection_amount(invoice, amount)
        return self.sudo().create_pending_payment(invoice, amount, "bank_transfer")

    def _orders_for_pending(self):
        invoices = self.invoice_ids
        return invoices.order_id | invoices.invoice_line_ids.sale_line_ids.order_id

    def _invalidate_order_pending(self):
        self._orders_for_pending().invalidate_recordset(["pending_amount"])

    @api.model
    def _check_portal_invoice(self, invoice):
        user = self.env.user
        commercial = invoice.partner_id.commercial_partner_id
        if commercial != user.partner_id.commercial_partner_id:
            raise AccessError(self.env._("This invoice belongs to another customer."))
        if invoice.state != "posted" or invoice.move_type not in ("out_invoice", "out_refund"):
            raise AccessError(self.env._("Only a posted invoice can be paid."))
