import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from odoo import fields, models
from odoo.tools import SQL

from odoo.addons.sol_commerce.constants.notifications import EVENT_INVOICE_OVERDUE
from odoo.addons.sol_commerce.services.payos_client import payos_client_from_env
from odoo.addons.sol_laboratory.constants.models import MODEL_JOB_ITEM, MODEL_JOB_RUN, MODEL_SCHEDULED_JOB
from odoo.addons.sol_laboratory.constants.notifications import VIETNAM_ZONE
from odoo.addons.sol_laboratory.models.system.scheduled_job import PermanentJobError

_logger = logging.getLogger(__name__)

POLL_AGAIN = timedelta(minutes=5)
PAYOS_LINK_EXISTS = "PayOS already has this order and did not return a checkout URL. Another link was not created."
# An unlinked bank account accepts 9 characters. A linked account is not a separate setting here.
PAYOS_DESCRIPTION_LIMIT = 9


class PayosLinkUnavailable(PermanentJobError):
    """PayOS already has this order. Creating another link would duplicate it."""


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model):
    _inherit = MODEL_SCHEDULED_JOB

    def _run_batch(self):
        if self.key == "overdue.reminders":
            self._queue_overdue_invoices()
        return super()._run_batch()

    def _queue_overdue_invoices(self):
        today = datetime.now(ZoneInfo(VIETNAM_ZONE)).date()
        invoices = self.env["account.move"].sudo().search([("is_overdue", "=", True)])
        for invoice in invoices:
            self.env[MODEL_SCHEDULED_JOB].queue(
                "overdue.reminders",
                f"{invoice.id}:{today.isoformat()}",
                document=invoice,
            )

    def _handle_payos_calls(self, item):
        transaction = item._document()
        if not transaction or transaction.payos_checkout_url:
            return None
        client = payos_client_from_env()
        if client is None:
            # The item stays queued. Setting the secrets later lets the same item continue.
            _logger.error("PayOS credentials are not set")
            return fields.Datetime.now() + POLL_AGAIN
        order_code = int(transaction._payos_order_code())
        amount = int(transaction.amount)
        checkout_url = self._payos_checkout_url(client, order_code, amount)
        if not checkout_url:
            return fields.Datetime.now() + POLL_AGAIN
        transaction.with_context(payment_safe_write=True).write({"payos_checkout_url": checkout_url})
        transaction.with_context(payment_safe_write=True)._set_pending()
        self.env[MODEL_SCHEDULED_JOB].queue("payos.poll", transaction.reference, document=transaction)
        return None

    def _payos_checkout_url(self, client, order_code, amount):
        # None is the HTTP 404. A timeout, 401, 403, 429 or 5xx raises and must not create a link.
        remote = client.request("GET", f"/v2/payment-requests/{order_code}")
        if remote is None:
            return self._payos_create_link(client, order_code, amount)
        data = remote.get("data") if isinstance(remote, dict) else None
        if not data:
            raise requests.HTTPError("PayOS did not confirm that this order is missing")
        if not self._payos_link_matches(data, amount, order_code):
            raise PermanentJobError("PayOS link does not match this payment")
        checkout_url = data.get("checkoutUrl")
        if checkout_url:
            return checkout_url
        raise PayosLinkUnavailable(PAYOS_LINK_EXISTS)

    def _process_item(self, item, handler, run):
        super()._process_item(item, handler, run)
        # The missing checkout URL fails inside the handler's savepoint, so the poll is queued after it.
        if item.status != "failed" or item.last_error != PAYOS_LINK_EXISTS:
            return
        document = item._document()
        if document:
            self.env[MODEL_SCHEDULED_JOB].queue("payos.poll", document.reference, document=document)

    def _payos_create_link(self, client, order_code, amount):
        base = self.env["ir.config_parameter"].sudo().get_str("web.base.url")
        return_url = f"{base}/payment/payos/return"
        description = self._payos_description(order_code)
        payload = {
            "orderCode": order_code,
            "amount": amount,
            "description": description,
            "cancelUrl": return_url,
            "returnUrl": return_url,
            "signature": client.payment_request_signature(amount, return_url, description, order_code, return_url),
        }
        body = client.request("POST", "/v2/payment-requests", payload) or {}
        data = body.get("data") or {}
        if ("orderCode" in data or "amount" in data) and not self._payos_link_matches(data, amount, order_code):
            raise PermanentJobError("PayOS link does not match this payment")
        return data.get("checkoutUrl")

    def _payos_description(self, order_code):
        """The bank memo is the order code. It is not cut down, and it fits an unlinked account."""
        description = str(int(order_code))
        if not description.isdigit() or len(description) > PAYOS_DESCRIPTION_LIMIT:
            raise PermanentJobError("The PayOS order code does not fit the payment description.")
        return description

    def _claim_pending_item(self, item):
        """Claim one pending item. A cron worker that already took it is left alone."""
        items = self.env[MODEL_JOB_ITEM].sudo()
        items.flush_model()
        self.env.cr.execute(
            SQL(
                """
                UPDATE %(table)s SET status = 'running', claimed_at = %(now)s
                WHERE id = %(item)s AND status = 'pending'
                RETURNING id
                """,
                table=SQL.identifier(items._table),
                now=fields.Datetime.now(),
                item=item.id,
            )
        )
        claimed = bool(self.env.cr.fetchone())
        item.invalidate_recordset(["status", "claimed_at"])
        return claimed

    def _run_claimed_item(self, item):
        """Run an item this request already claimed, using the cron's retry and failure rules."""
        self.ensure_one()
        now = fields.Datetime.now()
        run = self.env[MODEL_JOB_RUN].sudo().create({"job_id": self.id, "started_at": now})
        handler = getattr(self, self._handler_name(), None)
        if handler is None:
            run._finish("failed", f"No handler {self._handler_name()} is defined")
            return
        self._process_item(item, handler, run)
        run._close()

    def _payos_link_matches(self, data, amount, order_code):
        try:
            remote_amount = int(data.get("amount"))
            remote_code = int(data.get("orderCode"))
        except (TypeError, ValueError):
            return False
        return remote_amount == int(amount) and remote_code == int(order_code)

    def _handle_payos_poll(self, item):
        transaction = item._document()
        if not transaction:
            return None
        client = payos_client_from_env()
        if client is None:
            return fields.Datetime.now() + POLL_AGAIN
        order_code = transaction._payos_order_code()
        body = client.request("GET", f"/v2/payment-requests/{order_code}") or {}
        data = body.get("data") or body
        # amount on the payment request is what was asked. Money received is each transfer.
        self.env["payment.transaction"]._payos_record_transfers(order_code, data.get("transactions") or [])
        remaining = data.get("amountRemaining")
        if isinstance(remaining, (int, float)) and not isinstance(remaining, bool) and remaining > 0:
            return fields.Datetime.now() + POLL_AGAIN
        if data.get("status") == "PAID":
            return None
        if transaction._payos_expired() and not transaction.payos_bank_reference and transaction.state != "done":
            transaction.with_context(payment_safe_write=True)._process({"expired": True})
            return None
        return fields.Datetime.now() + POLL_AGAIN

    def _handle_overdue_reminders(self, item):
        invoice = item._document()
        today = datetime.now(ZoneInfo(VIETNAM_ZONE)).date()
        if not invoice or not invoice.is_overdue:
            return
        try:
            with self.env.cr.savepoint():
                self.env["mail.message"].raise_event(
                    EVENT_INVOICE_OVERDUE,
                    invoice,
                    f"invoice:{invoice.id}:overdue:{today.isoformat()}",
                    self.env._("Invoice %(name)s is overdue.", name=invoice.name or ""),
                    partners=invoice.partner_id,
                )
        except Exception:
            _logger.exception("Overdue reminder was not queued")
            raise
