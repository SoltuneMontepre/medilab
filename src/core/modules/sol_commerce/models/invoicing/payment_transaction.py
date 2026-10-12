from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from odoo.addons.sol_commerce.constants.models import MODEL_PAYMENT_TRANSACTION
from odoo.addons.sol_commerce.models.invoicing.res_config_settings import DEFAULT_PAYOS_EXPIRY_HOURS
from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS, MODEL_SCHEDULED_JOB


# Giao dịch thanh toán
class PaymentTransaction(models.Model):
    _inherit = MODEL_PAYMENT_TRANSACTION

    # The bank reference of this transfer. Empty until PayOS reports one.
    payos_bank_reference = fields.Char(copy=False)
    # The PayOS checkout page for the link. Empty until the call succeeds.
    payos_checkout_url = fields.Char(copy=False)
    # PayOS reported this transfer after the Vietnam day was locked.
    recorded_after_lock = fields.Boolean(copy=False)

    def _apply_updates(self, payment_data):
        if self.provider_code != "payos":
            return super()._apply_updates(payment_data)
        bank_reference = payment_data.get("bank_reference")
        if bank_reference:
            self.payos_bank_reference = bank_reference
        if payment_data.get("recorded_after_lock"):
            self.recorded_after_lock = True
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
        """Confirm a signed PayOS payment. A repeated bank reference does not create another transaction."""
        order_code = str(data.get("orderCode") or "")
        bank_reference = str(data.get("reference") or "")
        if not order_code or str(data.get("code")) != "00":
            return self.browse()
        locked = self.env["medilab.reconciliation.day"].sudo()._today_is_locked()
        if bank_reference:
            existing = self.search(
                [("payos_bank_reference", "=", bank_reference), ("provider_code", "=", "payos")], limit=1
            )
            if existing:
                return existing
        link = self.search([("reference", "=", order_code), ("provider_code", "=", "payos")], limit=1)
        if not link:
            return self.browse()
        target = link if not link.payos_bank_reference else self._payos_extra_transfer(link, bank_reference, data, locked)
        target.with_context(payment_safe_write=True)._process(
            {
                "paid": True,
                "amount": data.get("amount", target.amount),
                "bank_reference": bank_reference,
                "recorded_after_lock": locked,
            }
        )
        if target.state == "done":
            target._create_online_payment()
        return target

    def _payos_extra_transfer(self, link, bank_reference, data, recorded_after_lock=False):
        # The link keeps the order code. A later transfer is its own transaction so its money is not dropped.
        reference = bank_reference or self._compute_reference("payos", prefix=link.reference)
        return self.create(
            {
                "provider_id": link.provider_id.id,
                "payment_method_id": link.payment_method_id.id,
                "reference": reference,
                "provider_reference": link._payos_order_code(),
                "amount": data.get("amount") or link.amount,
                "currency_id": link.currency_id.id,
                "partner_id": link.partner_id.id,
                "operation": "online_redirect",
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

    def _create_online_payment(self):
        """Post the payment PayOS confirmed. The amount is PayOS's amount, even when it is more than the invoice."""
        self.ensure_one()
        if self.payment_id or self.state != "done" or not self.invoice_ids:
            return self.payment_id
        invoice = self.invoice_ids[:1]
        payment = self.env["account.payment"].sudo().create(
            {
                **self.env["account.payment"]._payment_values(invoice, self.amount, "online"),
                "payment_transaction_id": self.id,
            }
        )
        payment.action_post()
        self.with_context(payment_safe_write=True).write({"payment_id": payment.id})
        return payment
