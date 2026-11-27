import logging
from math import isfinite
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tools.misc import formatLang

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_PAYMENT, MODEL_PAYMENT_REQUEST
from odoo.addons.sol_commerce.constants.notifications import EVENT_PAYMENT_RECEIPT, EVENT_PAYMENT_REJECTED
from odoo.addons.sol_commerce.models.invoicing.account_move import ADMINISTRATOR_GROUP, BILLING_GROUP
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN
from odoo.addons.sol_laboratory.services.record_id import persisted_ids

if TYPE_CHECKING:
    from medilab_model_types import Model_account_payment as AccountPaymentBase
else:
    AccountPaymentBase = object

_logger = logging.getLogger(__name__)

METHOD_SELECTION = [("online", "Online"), ("bank_transfer", "Bank transfer"), ("cash", "Cash")]
METHODS = {method for method, _label in METHOD_SELECTION}
# States of a payment the accountant or the gateway confirmed; a draft is pending.
CONFIRMED_STATES = ("paid", "reconciled")
JOURNAL_TYPE = {"online": "bank", "bank_transfer": "bank", "cash": "cash"}
RECEIPT_TIME_REQUIRED_MESSAGE = "Enter the date and time the money was received."
POSITIVE_COLLECTION_AMOUNT_REQUIRED_MESSAGE = "Enter an amount greater than zero."


# Phiếu thu
class AccountPayment(models.Model, AccountPaymentBase):
    # _name is required to add a mixin to an Odoo model. The audit mixin comes first so it wraps Odoo's write.
    _name = MODEL_ACCOUNT_PAYMENT
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_ACCOUNT_PAYMENT]

    if not TYPE_CHECKING:
        # online, bank_transfer or cash.
        method = fields.Selection(METHOD_SELECTION, string="Collection Method")
        # Request the payment was reported against or applied to after review.
        payment_request_id = fields.Many2one(MODEL_PAYMENT_REQUEST, ondelete="restrict", index=True, copy=False)
        # When the customer transferred the funds or Sales received cash.
        received_at = fields.Datetime(copy=False)
        # Explanation of why an online transfer needs an accountant before it can apply.
        collection_review = fields.Selection(
            [("previous_request", "Previous request"), ("late", "After the deadline")], copy=False, readonly=True
        )
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
    def _create_request_payment(
        self, request, amount, method, received_at=None, reference=None, *, record_received=False
    ):
        order = request.order_id
        order._lock_payment_orders()
        if method not in METHODS - {"online"}:
            raise UserError(self.env._("Sales records cash and bank transfers. Online payments come from PayOS."))
        if record_received:
            if (
                order.payment_request_id != request
                or request.state not in ("open", "expired")
                or order.state == "cancel"
            ):
                raise UserError(self.env._("This payment request no longer takes new payments."))
        else:
            request._check_takes_payments()
        amount = self._validated_collection_amount(request, amount, subtract_pending=True)
        return self.create(
            {
                **self._payment_values(request, amount, method),
                "received_at": self._receipt_time(received_at),
                "memo": reference or request.quotation_id.code,
            }
        )

    @api.model
    def _receipt_time(self, received_at):
        now = fields.Datetime.now()
        try:
            received_at = fields.Datetime.to_datetime(received_at) if received_at else now
        except (TypeError, ValueError) as error:
            raise UserError(self.env._(RECEIPT_TIME_REQUIRED_MESSAGE)) from error
        if received_at is None:
            raise UserError(self.env._(RECEIPT_TIME_REQUIRED_MESSAGE))
        if received_at > now:
            raise UserError(self.env._("The receipt time cannot be in the future."))
        return received_at

    def _verified_for_request(self):
        return bool(self.reviewed_at and self.invoice_ids) and self.state not in ("draft", "canceled", "rejected")

    def _pending_manual_collection(self):
        return self.state == "draft" and self.method in ("cash", "bank_transfer")

    def _portal_receipts(self, invoice):
        """The confirmed payments among these whose receipt the portal user of the invoice's environment opens."""
        # A reader who sees the invoice only through its access token cannot open a receipt.
        if not invoice.has_access("read"):
            return self.browse()
        customer = invoice.sudo().partner_id.commercial_partner_id
        return self.filtered(
            lambda payment: (
                payment.state in CONFIRMED_STATES
                and invoice in payment.invoice_ids
                and payment.partner_id.commercial_partner_id == customer
            )
        ).sorted(lambda payment: (payment.date, payment.id))

    @api.model
    def _validated_collection_amount(self, invoice, amount, *, subtract_pending=False):
        """The amount a new payment may collect. An empty amount means the whole residual."""
        if invoice._name == MODEL_PAYMENT_REQUEST:
            residual = invoice.remaining_amount
            if subtract_pending:
                residual = max(invoice.currency_id.round(residual - invoice.pending_amount), 0)
        else:
            residual = invoice.amount_residual
        if self._amount_omitted(amount):
            amount = residual
        else:
            try:
                amount = float(amount)
            except (TypeError, ValueError) as error:
                raise UserError(self.env._(POSITIVE_COLLECTION_AMOUNT_REQUIRED_MESSAGE)) from error
        if not isfinite(amount):
            raise UserError(self.env._(POSITIVE_COLLECTION_AMOUNT_REQUIRED_MESSAGE))
        currency = invoice.currency_id
        amount = currency.round(amount)
        if currency.compare_amounts(amount, 0) <= 0:
            raise UserError(self.env._(POSITIVE_COLLECTION_AMOUNT_REQUIRED_MESSAGE))
        if currency.compare_amounts(amount, residual) > 0:
            raise UserError(self.env._("A payment cannot be more than the amount still owed."))
        return amount

    @api.model
    def _amount_omitted(self, amount):
        return amount is None or amount is False or (isinstance(amount, str) and not amount)

    def action_post(self):
        collections = self.filtered("method")
        if not collections:
            return super().action_post()
        self._check_billing()
        self.payment_request_id.order_id._lock_payment_orders()
        self._lock_invoices(self.invoice_ids)
        for payment in collections:
            prepared = payment._prepare_collection()
            super(AccountPayment, prepared).action_post()
            prepared._finish_collection()
        remaining = self - collections
        if remaining:
            return super(AccountPayment, remaining).action_post()
        return None

    def _prepare_collection(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(self.env._("Only a draft payment can be confirmed."))
        payment = self
        if self.payment_request_id:
            # Sales can draft the payment, but posting and reconciling touch protected order and invoice lines.
            payment = self.sudo()
            payment._prepare_request_collection()
        else:
            self._check_collection_amount()
        payment.write({"reviewed_by_id": self.env.user.id, "reviewed_at": fields.Datetime.now()})
        return payment

    def _finish_collection(self):
        self._reconcile_with_invoices()
        if self.payment_request_id:
            self.payment_request_id._refresh_funding()
        self._queue_customer_notice(EVENT_PAYMENT_RECEIPT, "receipt")

    def _prepare_request_collection(self):
        request = self.payment_request_id
        order = request.order_id
        if self.collection_review == "previous_request":
            request = order.payment_request_id
        if not request or request.state == "superseded" or order.state == "cancel":
            raise UserError(self.env._("This collection needs a current payment request before it can be applied."))
        if not self.received_at:
            raise UserError(self.env._(RECEIPT_TIME_REQUIRED_MESSAGE))
        if request.deadline and self.received_at > request.deadline:
            raise UserError(self.env._("Sales must extend the payment deadline before this collection can be applied."))
        if self.method != "online":
            self._validated_collection_amount(request, self.amount)
        elif request.currency_id.compare_amounts(self.amount, request.remaining_amount) > 0:
            self.exceeds_residual = True
        if request.kind == "advance" or request.remaining_amount:
            invoice = order._create_collection_invoice(request, self.amount)
            self.invoice_ids = [Command.set(persisted_ids(invoice))]
            self.payment_transaction_id.with_context(payment_safe_write=True).invoice_ids = self.invoice_ids
        self.payment_request_id = request

    def action_reject_payment(self):
        """Cancel a draft payment and leave the reason as an activity for the salesperson."""
        self.ensure_one()
        self._check_billing()
        self.payment_request_id.order_id._lock_payment_orders()
        self._lock_invoices(self.invoice_ids)
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
        if "received_at" in vals:
            online = self.filtered(
                lambda payment: payment.method == "online" or payment.payment_transaction_id.provider_code == "payos"
            )
            received_at = fields.Datetime.to_datetime(vals["received_at"]) or False
            if any(payment.received_at != received_at for payment in online):
                raise UserError(self.env._("The receipt time of an online payment cannot be changed."))
        frozen = self.filtered(
            lambda payment: payment.method == "online" and payment.state != "draft" and payment._online_day_locked()
        )
        changed = {"amount", "partner_id", "journal_id", "method", "date"} & set(vals)
        if frozen and (changed or vals.get("state") in {"draft", "canceled", "rejected"}):
            raise UserError(self.env._("An online payment of a locked day cannot be changed."))
        if vals.get("state") in {"draft", "canceled", "rejected"}:
            self._check_verified_request_reversal()
        orders = self._orders_for_pending()
        result = super().write(vals)
        (orders | self._orders_for_pending()).invalidate_recordset(["pending_amount"])
        return result

    def unlink(self):
        self._check_verified_request_reversal()
        return super().unlink()

    def _check_verified_request_reversal(self):
        linked = self.sudo().filtered("payment_request_id")
        linked.payment_request_id.order_id._lock_payment_orders()
        if any(payment._verified_for_request() for payment in linked):
            raise UserError(self.env._("A verified payment request collection cannot be reversed."))

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
        salesperson = self.payment_request_id.order_id.user_id or self.invoice_ids.invoice_user_id[:1]
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
        # The notice goes to the customer, in their language and with the amount written as money.
        env = self.with_context(lang=partner.lang or self.env.lang).env
        amount = formatLang(env, self.amount, currency_obj=self.currency_id)
        body = env._("Payment of %(amount)s was recorded.", amount=amount)
        if kind == "rejected":
            body = env._("Payment was rejected: %(reason)s", reason=self.rejection_reason or "")
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
        values = {
            "amount": amount,
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": invoice.partner_id.id,
            "currency_id": invoice.currency_id.id,
            "journal_id": journal.id,
            "method": method,
        }
        if invoice._name == MODEL_PAYMENT_REQUEST:
            return {**values, "payment_request_id": invoice.id, "memo": invoice.quotation_id.code}
        return {**values, "invoice_ids": [Command.set(persisted_ids(invoice))], "memo": invoice.name}

    @api.model
    def _portal_pay_request(self, request, amount=None, received_at=None, reference=None):
        order = request.order_id
        order._lock_payment_orders()
        request._check_takes_payments()
        existing = self.sudo().search(
            [("payment_request_id", "=", request.id), ("method", "=", "bank_transfer"), ("state", "=", "draft")],
            limit=1,
        )
        if existing:
            raise UserError(self.env._("A bank transfer is already pending for this payment request."))
        return self.sudo()._create_request_payment(request, amount, "bank_transfer", received_at, reference)

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
        return self.payment_request_id.order_id | invoices.order_id | invoices.invoice_line_ids.sale_line_ids.order_id

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
