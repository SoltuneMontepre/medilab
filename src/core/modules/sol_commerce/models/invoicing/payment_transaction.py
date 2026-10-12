from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_PAYMENT, MODEL_PAYMENT_TRANSACTION
from odoo.addons.sol_commerce.models.invoicing.res_config_settings import DEFAULT_PAYOS_EXPIRY_HOURS
from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS, MODEL_SCHEDULED_JOB


# Giao dịch thanh toán
class PaymentTransaction(models.Model):
    _inherit = MODEL_PAYMENT_TRANSACTION

    # The bank reference of this transfer. Empty until PayOS reports one.
    payos_bank_reference = fields.Char(copy=False, index=True)
    # The PayOS checkout page for the link. Empty until the call succeeds.
    payos_checkout_url = fields.Char(copy=False)
    # When PayOS says the bank transfer happened, stored in UTC.
    payos_transferred_at = fields.Datetime(copy=False)
    # PayOS reported this transfer after its Vietnam day was locked.
    recorded_after_lock = fields.Boolean(copy=False)
    # exact, partial or over, from the payment against the invoice.
    payos_settlement = fields.Selection(
        [("exact", "Exact"), ("partial", "Partial"), ("over", "Over")],
        compute="_compute_payos_settlement",
    )

    _payos_transfer_unique = models.Constraint(
        "UNIQUE(payos_bank_reference)",
        "A PayOS bank transfer is recorded once.",
    )

    @api.depends(
        "provider_code", "state", "payment_id.exceeds_residual", "payment_id.amount", "invoice_ids.amount_total"
    )
    def _compute_payos_settlement(self):
        for transaction in self:
            payment = transaction.payment_id
            if transaction.provider_code != "payos" or transaction.state != "done" or not payment:
                transaction.payos_settlement = False
            elif payment.exceeds_residual:
                transaction.payos_settlement = "over"
            elif payment.amount < sum(transaction.invoice_ids.mapped("amount_total")):
                transaction.payos_settlement = "partial"
            else:
                transaction.payos_settlement = "exact"

    def _apply_updates(self, payment_data):
        if self.provider_code != "payos":
            return super()._apply_updates(payment_data)
        bank_reference = payment_data.get("bank_reference")
        if bank_reference:
            self.payos_bank_reference = bank_reference
        if payment_data.get("recorded_after_lock"):
            self.recorded_after_lock = True
        if payment_data.get("transferred_at"):
            self.payos_transferred_at = payment_data["transferred_at"]
        if payment_data.get("amount") is not None:
            self.amount = payment_data["amount"]
        if payment_data.get("paid"):
            self._set_done(extra_allowed_states=("cancel",))
        elif payment_data.get("expired"):
            self._set_canceled()
        return None

    def _extract_amount_data(self, payment_data):
        if self.provider_code != "payos":
            return super()._extract_amount_data(payment_data)
        if payment_data.get("amount") is None:
            return None
        return {"amount": payment_data["amount"], "currency_code": self.currency_id.name}

    def _payos_order_code(self):
        self.ensure_one()
        return self.provider_reference or self.reference

    def _payos_expired(self):
        self.ensure_one()
        hours = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("payos_expiry_hours") or DEFAULT_PAYOS_EXPIRY_HOURS
        return fields.Datetime.now() > self.create_date + timedelta(hours=hours)

    @api.model
    def _payos_apply_webhook(self, data):
        """Record one signed transfer. The payment-request amount is not money received."""
        if not isinstance(data, dict) or str(data.get("code")) != "00":
            return self.browse()
        order_code = str(data.get("orderCode") or "")
        if not order_code:
            return self.browse()
        return self._payos_record_transfers(order_code, [data])

    @api.model
    def _payos_record_transfers(self, order_code, transfers):
        """Record each bank transfer once. The same reference updates nothing a second time."""
        order_code = str(order_code)
        link = self.search([("reference", "=", order_code), ("provider_code", "=", "payos")], limit=1)
        if not link:
            return self.browse()
        self.env[MODEL_ACCOUNT_PAYMENT]._lock_invoices(link.invoice_ids)
        self._payos_lock_order(order_code)
        link = self.search([("reference", "=", order_code), ("provider_code", "=", "payos")], limit=1)
        recorded = self.browse()
        for transfer in transfers:
            recorded |= self._payos_record_one(link, transfer)
        return recorded

    def _payos_record_one(self, link, transfer):
        reference = str(transfer.get("reference") or "").strip()
        amount = transfer.get("amount")
        # A missing reference must not be stored on the link, or the next transfer would look like this one.
        if not reference or not isinstance(amount, (int, float)) or isinstance(amount, bool):
            return self.browse()
        days = self.env["medilab.reconciliation.day"]
        moment = days._payos_moment(transfer.get("transactionDateTime"))
        locked = bool(moment) and days._day_is_locked(days._vietnam_day(moment))
        values = {
            "paid": True,
            "amount": amount,
            "bank_reference": reference,
            "transferred_at": moment,
            "recorded_after_lock": locked,
        }
        existing = self.search([("payos_bank_reference", "=", reference)], limit=1)
        if existing:
            if existing.state != "done":
                existing.with_context(payment_safe_write=True)._process(values)
            if existing.state == "done" and not existing.payment_id:
                existing._create_online_payment()
            return existing
        if not link.payos_bank_reference:
            target = link
        else:
            try:
                with self.env.cr.savepoint():
                    target = self._payos_extra_transfer(link, reference, amount, locked, moment)
            except IntegrityError:
                return self.search([("payos_bank_reference", "=", reference)], limit=1)
        target.with_context(payment_safe_write=True)._process(values)
        if target.state == "done":
            target._create_online_payment()
        return target

    @api.model
    def _payos_lock_order(self, order_code):
        self.env.cr.execute(
            """
            SELECT payment_transaction.id
            FROM payment_transaction
            JOIN payment_provider ON payment_provider.id = payment_transaction.provider_id
            WHERE payment_provider.code = 'payos'
              AND (payment_transaction.reference = %s OR payment_transaction.provider_reference = %s)
            ORDER BY payment_transaction.id
            FOR UPDATE OF payment_transaction
            """,
            (order_code, order_code),
        )

    def _payos_extra_transfer(self, link, bank_reference, amount, recorded_after_lock, transferred_at):
        # The link keeps the order code. A later transfer is its own transaction so its money is not dropped.
        return self.create(
            {
                "provider_id": link.provider_id.id,
                "payment_method_id": link.payment_method_id.id,
                "reference": bank_reference,
                "provider_reference": link._payos_order_code(),
                "amount": amount,
                "currency_id": link.currency_id.id,
                "partner_id": link.partner_id.id,
                "operation": "online_redirect",
                "payos_bank_reference": bank_reference,
                "payos_transferred_at": transferred_at,
                "recorded_after_lock": recorded_after_lock,
                "invoice_ids": [Command.set(link.invoice_ids.ids)],
            }
        )

    def action_payos_checkout(self):
        """Queue the PayOS call that creates the payment link. The return URL does not confirm it."""
        self.ensure_one()
        provider = self.env.ref("sol_commerce.payment_provider_payos")
        if not provider.is_published:
            raise UserError(self.env._("PayOS is turned off."))
        self.env[MODEL_SCHEDULED_JOB].queue("payos.calls", self.reference, document=self)
        return self

    @api.model
    def _create_payos_transaction(self, invoice):
        provider = self.env.ref("sol_commerce.payment_provider_payos")
        method = self.env.ref("sol_commerce.payment_method_payos_qr")
        order_code = self.env["ir.sequence"].next_by_code("medilab.payos.order")
        transaction = self.create(
            {
                "provider_id": provider.id,
                "payment_method_id": method.id,
                "reference": order_code,
                "provider_reference": order_code,
                "amount": invoice.amount_residual,
                "currency_id": invoice.currency_id.id,
                "partner_id": invoice.partner_id.id,
                "operation": "online_redirect",
                "invoice_ids": [Command.set(invoice.ids)],
            }
        )
        return transaction.action_payos_checkout()

    @api.model
    def portal_start_payos(self, invoice):
        """Start PayOS for the customer's invoice. A second click reuses the open link."""
        self.env[MODEL_ACCOUNT_PAYMENT]._lock_invoices(invoice)
        if not invoice._portal_payos_available():
            raise UserError(self.env._("PayOS is turned off."))
        existing = self.sudo().search(
            [
                ("invoice_ids", "in", invoice.ids),
                ("provider_code", "=", "payos"),
                ("state", "in", ("draft", "pending")),
                ("payment_id", "=", False),
            ],
            limit=1,
        )
        if existing:
            return existing
        if invoice.amount_residual <= 0:
            raise UserError(self.env._("This invoice is already paid."))
        return self.sudo()._create_payos_transaction(invoice)

    def _create_online_payment(self):
        """Post the payment PayOS confirmed. The amount is PayOS's amount, even when it is more than the invoice."""
        self.ensure_one()
        if self.payment_id or self.state != "done" or not self.invoice_ids:
            return self.payment_id
        invoice = self.invoice_ids[:1]
        payment = (
            self.env[MODEL_ACCOUNT_PAYMENT]
            .sudo()
            .create(
                {
                    **self.env[MODEL_ACCOUNT_PAYMENT]._payment_values(invoice, self.amount, "online"),
                    "payment_transaction_id": self.id,
                }
            )
        )
        payment.action_post()
        self.with_context(payment_safe_write=True).write({"payment_id": payment.id})
        return payment
