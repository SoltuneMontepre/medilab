import logging
import re
from datetime import UTC, datetime, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import SQL

from odoo.addons.commerce.constants.models import (
    MODEL_INVOICE,
    MODEL_PAYMENT_LINK,
    MODEL_PAYMENT_LINK_TRANSACTION,
    MODEL_VND_MIXIN,
)
from odoo.addons.commerce.constants.payos import (
    CANCEL_ROUTE,
    CHECKOUT_URL_FORMAT,
    DESCRIPTION_MAX_LENGTH,
    FINAL_STATUSES,
    JOB_CALLS,
    JOB_POLL,
    PAYOS_TIMEZONE,
    POLL_GRACE_MINUTES,
    POLL_INTERVAL_MINUTES,
    RETURN_ROUTE,
    STATUS_MAP,
    STATUS_ORDER,
    SUCCESS_CODE,
)
from odoo.addons.commerce.models.system.res_config_settings import PAYOS_ENABLED, PAYOS_LINK_EXPIRY_HOURS
from odoo.addons.commerce.services.payos_client import PayosClient, PayosError, PayosUnavailable
from odoo.addons.laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_IR_CONFIG_PARAMETER,
    MODEL_IR_SEQUENCE,
    MODEL_JOB_ITEM,
    MODEL_PERMISSION_MIXIN,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.laboratory.models.system.scheduled_job import PermanentJobError

_logger = logging.getLogger(__name__)

# Context key of the writes made from what PayOS reported; the reconciliation lock lets only those through.
PROVIDER_UPDATE_KEY = "payos_provider_update"
OPEN_STATUSES = ("created", "pending")


# Liên Kết Thanh Toán
class PaymentLink(models.Model):
    _name = MODEL_PAYMENT_LINK
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_VND_MIXIN]
    _description = "Payment Link"
    _order = "create_date desc, id desc"
    # A link is evidence of what was asked of PayOS, so nobody deletes one.
    _permission_actions = ("read", "create", "edit")

    # The invoice the link pays.
    invoice_id = fields.Many2one(MODEL_INVOICE, required=True, ondelete="restrict", index=True)
    # The customer billed; kept on the invoice.
    partner_id = fields.Many2one(related="invoice_id.partner_id")
    # Order code sent to PayOS, from the sequence medilab.payment.link; unique, so a notification finds its link.
    provider_order_code = fields.Integer(required=True, readonly=True, copy=False, index=True)
    # Amount the link asks for.
    amount = fields.Monetary(required=True)
    # Checkout page PayOS returned; empty while the creation waits in the job queue after an outage.
    checkout_url = fields.Char(readonly=True, copy=False)
    # created, pending, paid, failed, cancelled or expired; moves forward only.
    status = fields.Selection(
        [
            ("created", "Created"),
            ("pending", "Pending"),
            ("paid", "Paid"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
            ("expired", "Expired"),
        ],
        required=True,
        default="created",
        index=True,
        copy=False,
    )
    # When the link stops being payable at PayOS.
    expires_at = fields.Datetime(required=True)
    # Id PayOS gave the link.
    provider_payment_link_id = fields.Char(string="PayOS link id", readonly=True, copy=False)
    # Transfers PayOS reported for the link.
    transaction_ids = fields.One2many(MODEL_PAYMENT_LINK_TRANSACTION, "link_id", string="Transactions")
    # Sum of the transfers PayOS reported.
    amount_paid = fields.Monetary(compute="_compute_amount_paid", store=True)

    _order_code_unique = models.Constraint(
        "UNIQUE(provider_order_code)", "A payment link with this order code already exists."
    )
    _amount_positive = models.Constraint("CHECK(amount > 0)", "A payment link asks for a positive amount.")

    @api.depends("transaction_ids.amount")
    def _compute_amount_paid(self):
        for link in self:
            link.amount_paid = link.currency_id.round(sum(link.transaction_ids.mapped("amount")))

    @api.depends("invoice_id.code", "provider_order_code")
    def _compute_display_name(self):
        for link in self:
            link.display_name = f"{link.invoice_id.display_name} #{link.provider_order_code}"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("provider_order_code"):
                vals["provider_order_code"] = self._next_order_code()
        return super().create(vals_list)

    @api.model
    def _next_order_code(self):
        number = self.env[MODEL_IR_SEQUENCE].sudo().next_by_code(MODEL_PAYMENT_LINK)
        if not number or not number.isdigit():
            raise UserError(
                self.env._("The payment link order code must be a number; check its format in Code formats.")
            )
        return int(number)

    def _in_use_domain(self):
        return Domain("status", "in", OPEN_STATUSES)

    @api.model
    def _description_for(self, invoice):
        # PayOS limits the transfer description to 9 characters for unlinked bank accounts, and banks drop spaces
        # and slashes: the digits come first so a long prefix is dropped before the number and the year.
        code = invoice.code or ""
        digits = re.sub(r"\D", "", code)
        letters = re.sub(r"[^A-Za-z]", "", code).upper()
        return (digits + letters)[:DESCRIPTION_MAX_LENGTH]

    @api.model
    def _check_payos_available(self):
        if not self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter(PAYOS_ENABLED):
            raise UserError(self.env._("PayOS payments are turned off in the settings."))
        if not PayosClient().is_configured():
            raise UserError(
                self.env._(
                    "PayOS credentials are not configured: set PAYOS_CLIENT_ID, PAYOS_API_KEY and "
                    "PAYOS_CHECKSUM_KEY in the environment."
                )
            )

    @api.model
    def _create_for_invoice(self, invoice, amount, expires_at=None):
        """Ask PayOS for a link paying this amount of the invoice; an outage queues the call instead."""
        self.check_access("create")
        self._check_payos_available()
        if invoice.status != "posted" or invoice.kind == "adjustment":
            raise UserError(self.env._("A payment link pays a posted advance or final invoice."))
        currency = invoice.currency_id
        if currency.compare_amounts(amount, 0) <= 0 or currency.compare_amounts(amount, invoice.amount_owed) > 0:
            raise UserError(
                self.env._("The amount must be positive and at most what is still owed on %s.", invoice.display_name)
            )
        if expires_at is None:
            hours = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter(PAYOS_LINK_EXPIRY_HOURS)
            expires_at = fields.Datetime.now() + timedelta(hours=hours)
        link = self.create({"invoice_id": invoice.id, "amount": amount, "expires_at": expires_at})
        link._request_creation()
        return link

    def _request_creation(self):
        # No row lock is held here: an HTTP call never runs under one. An outage queues the call; any other
        # refusal is shown to the user and the link is not kept.
        self.ensure_one()
        try:
            data = PayosClient().create_payment_link(**self._creation_arguments())
        except PayosUnavailable as error:
            _logger.warning("PayOS unreachable, creation of link %s queued: %s", self.provider_order_code, error)
            self._queue_call("create")
        except PayosError as error:
            raise UserError(self.env._("PayOS refused the payment link: %s", error)) from error
        else:
            self._adopt(data)

    def _creation_arguments(self):
        base_url = self.env[MODEL_IR_CONFIG_PARAMETER].sudo().get_str("web.base.url")
        return {
            "order_code": self.provider_order_code,
            "amount": int(self.amount),
            "description": self._description_for(self.invoice_id),
            "return_url": base_url + RETURN_ROUTE,
            "cancel_url": base_url + CANCEL_ROUTE,
            "expired_at": int(self.expires_at.replace(tzinfo=UTC).timestamp()),
        }

    def _adopt(self, data):
        """Take what PayOS knows of the link: its id, checkout page, status and transfers, then watch it."""
        self.ensure_one()
        vals = {}
        payment_link_id = data.get("paymentLinkId") or data.get("id")
        if payment_link_id and not self.provider_payment_link_id:
            vals["provider_payment_link_id"] = payment_link_id
        checkout_url = data.get("checkoutUrl") or (payment_link_id and CHECKOUT_URL_FORMAT.format(payment_link_id))
        if checkout_url and not self.checkout_url:
            vals["checkout_url"] = checkout_url
        if vals:
            self.sudo().write(vals)
        self._apply_provider_update(data.get("transactions") or [], data.get("status") or "PENDING")
        self._queue_poll()

    def _queue_call(self, call):
        return self.env[MODEL_SCHEDULED_JOB].queue(
            JOB_CALLS, f"{call}:{self.id}", document=self, payload={"call": call}
        )

    def _queue_poll(self):
        return self.env[MODEL_SCHEDULED_JOB].queue(JOB_POLL, f"poll:{self.id}", document=self)

    def action_cancel(self):
        self._check_permission("edit")
        statuses = dict(self._fields["status"]._description_selection(self.env))
        for link in self:
            if link.status not in OPEN_STATUSES:
                raise UserError(
                    self.env._(
                        "%(link)s is already %(status)s.", link=link.display_name, status=statuses[link.status].lower()
                    )
                )
            link._cancel_at_provider()

    def _cancel_at_provider(self):
        # Called from the form with no row lock held; an outage queues the call.
        self.ensure_one()
        if self.provider_payment_link_id:
            try:
                PayosClient().cancel_payment_link(self.provider_order_code)
            except PayosUnavailable as error:
                _logger.warning(
                    "PayOS unreachable, cancellation of link %s queued: %s", self.provider_order_code, error
                )
                self._queue_call("cancel")
            except PayosError as error:
                # Unknown at PayOS or already final there; a paid link is settled by the poll.
                _logger.info("PayOS did not cancel link %s: %s", self.provider_order_code, error)
        else:
            # Never created at PayOS: the queued creation is dropped instead.
            self._queued_items("create").action_cancel()
        self._advance_status("cancelled")

    def _queued_items(self, call):
        return (
            self.env[MODEL_JOB_ITEM]
            .sudo()
            .search(
                [
                    ("job_id.key", "=", JOB_CALLS),
                    ("item_key", "=", f"{call}:{self.id}"),
                    ("status", "in", ("pending", "failed")),
                ]
            )
        )

    def _advance_status(self, status):
        # Statuses move forward only; paid is final, so a cancelled or expired reported later is ignored, and
        # PayOS's paid wins over a cancelled or expired set locally.
        for link in self.sudo():
            if STATUS_ORDER[status] > STATUS_ORDER[link.status]:
                link.write({"status": status})

    def _lock_invoice(self):
        # Every path that moves money locks the invoice row first, then touches links, transactions and payments.
        self.env.cr.execute(
            SQL(
                "SELECT id FROM %(table)s WHERE id = %(id)s FOR NO KEY UPDATE",
                table=SQL.identifier(self.env[MODEL_INVOICE]._table),
                id=self.invoice_id.id,
            )
        )

    def _apply_provider_update(self, transactions, status=None):
        """Store what PayOS reported: each transfer once by its reference, then the status; safe to repeat."""
        self.ensure_one()
        link = self.sudo().with_context(**{PROVIDER_UPDATE_KEY: True})
        link._lock_invoice()
        link._store_transactions(transactions)
        if status is None:
            # A notification carries one transfer and no link status: the sum tells whether the link is paid.
            new_status = "paid" if link.currency_id.compare_amounts(link.amount_paid, link.amount) >= 0 else "pending"
        else:
            new_status = STATUS_MAP.get(status)
            if new_status is None:
                _logger.warning("PayOS reported the unknown status %r for link %s", status, link.provider_order_code)
        if new_status:
            link._advance_status(new_status)
        link._record_payments()
        return link

    def _store_transactions(self, transactions):
        references = [data.get("reference") for data in transactions if data.get("reference")]
        model = self.env[MODEL_PAYMENT_LINK_TRANSACTION]
        stored = set(model.search([("reference", "in", references)]).mapped("reference"))
        for data in transactions:
            reference = data.get("reference")
            if not reference or reference in stored:
                continue
            model.create(
                {
                    "link_id": self.id,
                    "reference": reference,
                    "amount": data.get("amount") or 0,
                    "transacted_at": self._parse_transaction_time(data.get("transactionDateTime")),
                }
            )
            stored.add(reference)

    @api.model
    def _parse_transaction_time(self, value):
        # PayOS gives "2026-03-03 10:15:00" with no timezone: read as Vietnam time, stored in UTC like every Datetime.
        if not value:
            return fields.Datetime.now()
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = pytz.timezone(PAYOS_TIMEZONE).localize(parsed)
        return parsed.astimezone(UTC).replace(tzinfo=None)

    def _record_payments(self):
        """Hook of the payments feature: one online payment per transfer without one, under the invoice lock."""

    @api.model
    def _handle_webhook(self, data):
        """Apply a verified PayOS notification; an unknown order code is ignored, which answers PayOS's test ping."""
        try:
            order_code = int(data.get("orderCode"))
        except (TypeError, ValueError):
            return False
        link = self.sudo().search([("provider_order_code", "=", order_code)], limit=1)
        if not link:
            return False
        if data.get("code") != SUCCESS_CODE:
            _logger.info("PayOS notified link %s with code %s: %s", order_code, data.get("code"), data.get("desc"))
            return True
        if data.get("paymentLinkId") and not link.provider_payment_link_id:
            link.write({"provider_payment_link_id": data["paymentLinkId"]})
        link._apply_provider_update([data])
        link._queue_poll()
        return True

    def _replay_creation(self):
        """Job handler of create:<id>: create at PayOS, or adopt the link PayOS already knows under the order code."""
        self.ensure_one()
        if self.status != "created":
            return
        try:
            data = PayosClient().create_payment_link(**self._creation_arguments())
        except PayosUnavailable:
            raise
        except PayosError as refusal:
            data = self._known_at_provider(refusal)
        self._adopt(data)

    def _known_at_provider(self, refusal):
        # PayOS publishes no code for "the order already exists", so any refusal asks whether the link exists:
        # the same amount means the timed-out first call succeeded, another amount means a collision.
        try:
            data = PayosClient().get_payment_link(self.provider_order_code)
        except PayosUnavailable:
            raise
        except PayosError:
            raise refusal from None
        if self.currency_id.compare_amounts(data.get("amount") or 0, self.amount) != 0:
            raise PermanentJobError(
                f"Order code {self.provider_order_code} exists at PayOS with the amount {data.get('amount')} instead "
                f"of {self.amount:.0f}; environments may share a PayOS merchant, see Code formats"
            )
        return data

    def _replay_cancel(self):
        """Job handler of cancel:<id>: cancel at PayOS unless the link was paid meanwhile."""
        self.ensure_one()
        if self.status == "paid":
            return
        try:
            PayosClient().cancel_payment_link(self.provider_order_code)
        except PayosUnavailable:
            raise
        except PayosError as error:
            _logger.info("PayOS did not cancel link %s: %s", self.provider_order_code, error)
        self._advance_status("cancelled")

    def _poll(self):
        """Job handler of poll:<id>: take the status and transfers from PayOS; returns when to ask again."""
        self.ensure_one()
        if self.status in FINAL_STATUSES:
            return None
        now = fields.Datetime.now()
        data = PayosClient().get_payment_link(self.provider_order_code)
        self._apply_provider_update(data.get("transactions") or [], data.get("status"))
        if self.status in FINAL_STATUSES:
            return None
        if now > self.expires_at + timedelta(minutes=POLL_GRACE_MINUTES):
            # PayOS has not reported the expiry itself; a paid reported later still wins.
            self._advance_status("expired")
            return None
        return now + timedelta(minutes=POLL_INTERVAL_MINUTES)
