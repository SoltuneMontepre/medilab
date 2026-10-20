from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.fields import Command

from odoo.addons.sol_commerce.models.orders.sale_order_confirmation import CONFIRMING_ORDER_IDS
from odoo.addons.sol_laboratory.constants.notifications import VIETNAM_ZONE

MARKER = "sol_demo.demo_account_move_advance"
PARTNER_AN_PHU = "sol_demo.demo_res_partner_an_phu"
MODEL_ACCOUNT_PAYMENT = "account.payment"
MODEL_PRODUCT = "product.product"
MODEL_TAX = "account.tax"
MODEL_TRANSACTION = "payment.transaction"
LEAD_IN_WATER = "Lead in water"
VAT_EIGHT = "VAT 8%"


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.model
    def _seed_notification_demo(self):
        """Posted invoices, payments and notification rows for a walkthrough. Safe to run again."""
        if self.env.ref(MARKER, raise_if_not_found=False):
            self._seed_two_rate_invoice()
            self._seed_payos_advance()
            self._seed_failed_push()
            return
        company = self.env.company
        if not company.chart_template:
            self.env["account.chart.template"].try_loading("vn", company)
        if not self.env["account.journal"].search([("type", "=", "sale"), ("company_id", "=", company.id)], limit=1):
            return
        an_phu = self.env.ref(PARTNER_AN_PHU)
        green = self.env.ref("sol_demo.demo_res_partner_green_farm")
        if not an_phu.email:
            an_phu.email = "ketoan@anphu-beverage.example"
        if not green.email:
            green.email = "ketoan@greenfarm.example"
        product = self.env[MODEL_PRODUCT].create(
            {
                "name": LEAD_IN_WATER,
                "type": "service",
                "list_price": 5_000_000,
                "invoice_policy": "order",
                "taxes_id": [Command.clear()],
            }
        )
        vat8 = self.env[MODEL_TAX].create(
            {
                "name": VAT_EIGHT,
                "amount": 8,
                "amount_type": "percent",
                "type_tax_use": "sale",
                "price_include_override": "tax_excluded",
            }
        )
        vat10 = self.env[MODEL_TAX].create(
            {
                "name": "VAT 10%",
                "amount": 10,
                "amount_type": "percent",
                "type_tax_use": "sale",
                "price_include_override": "tax_excluded",
            }
        )
        order = self._demo_order(an_phu, product, vat8)
        advance = order.create_advance_invoice(amount=2_500_000)
        final = order.create_final_invoice()
        final.action_post()
        raising = advance.action_adjust(200_000)
        lowering = final.action_adjust(-100_000)
        draft = self._demo_invoice(green, product, vat10, "draft")
        cancelled = self._demo_invoice(green, product, vat10, "cancel")
        payments = self.env[MODEL_ACCOUNT_PAYMENT]
        cash = payments.create_pending_payment(advance, 1_000_000, "cash")
        cash.action_post()
        transfer = payments.create_pending_payment(advance, 500_000, "bank_transfer")
        pending = payments.create_pending_payment(final, 200_000, "bank_transfer")
        rejected = payments.create_pending_payment(final, 100_000, "cash")
        rejected.rejection_reason = "The cash was not received"
        rejected.action_reject_payment()
        yesterday = datetime.now(ZoneInfo(VIETNAM_ZONE)).date() - timedelta(days=2)
        overdue = self._demo_invoice(an_phu, product, vat8, "draft")
        overdue.invoice_date_due = yesterday
        overdue.action_post()
        self.env["medilab.scheduled.job"]._run_key("overdue.reminders")
        self._demo_payos_days(final)
        self._demo_portal_users(an_phu, green)
        self._remember(
            {
                "demo_account_move_advance": advance,
                "demo_account_move_final": final,
                "demo_account_move_raising": raising,
                "demo_account_move_lowering": lowering,
                "demo_account_move_draft": draft,
                "demo_account_move_cancelled": cancelled,
                "demo_account_move_overdue": overdue,
                "demo_account_payment_cash": cash,
                "demo_account_payment_transfer": transfer,
                "demo_account_payment_pending": pending,
                "demo_account_payment_rejected": rejected,
            }
        )
        self._demo_notification_rows()
        self._seed_two_rate_invoice()
        self._seed_payos_advance()
        self._seed_failed_push()

    def _demo_order(self, partner, product, tax):
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "order_line": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_uom_qty": 1,
                            "price_unit": 5_000_000,
                            "tax_ids": [Command.set(tax.ids)],
                        }
                    )
                ],
            }
        )
        # This walkthrough needs an accounting order. Customer confirmation stays on the order demo.
        token = CONFIRMING_ORDER_IDS.set(frozenset(order.ids))
        try:
            order.action_confirm()
        finally:
            CONFIRMING_ORDER_IDS.reset(token)
        return order

    def _demo_invoice(self, partner, product, tax, state):
        invoice = self.create(
            {
                "move_type": "out_invoice",
                "invoice_kind": "final",
                "partner_id": partner.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "quantity": 1,
                            "price_unit": 1_000_000,
                            "tax_ids": [Command.set(tax.ids)],
                        }
                    )
                ],
            }
        )
        if state == "posted":
            invoice.action_post()
        elif state == "cancel":
            invoice.button_cancel()
        return invoice

    def _demo_payos_days(self, invoice):
        provider = self.env.ref("sol_commerce.payment_provider_payos", raise_if_not_found=False)
        if not provider:
            return
        provider.is_published = True
        method = self.env.ref("sol_commerce.payment_method_payos_qr", raise_if_not_found=False)
        if method:
            method.active = True
        reconciliation_days = self.env["medilab.reconciliation.day"]
        now = fields.Datetime.to_datetime("2020-01-03 03:00:00")
        product = invoice.invoice_line_ids.product_id[:1]
        tax = invoice.invoice_line_ids.tax_ids[:1]
        locked_invoice = self._demo_invoice(invoice.partner_id, product, tax, "posted")
        open_invoice = self._demo_invoice(invoice.partner_id, product, tax, "posted")
        locked_tx = self.env[MODEL_TRANSACTION]._create_payos_transaction(locked_invoice)
        locked_moment = fields.Datetime.to_datetime("2020-01-02 03:00:00")
        locked_tx.with_context(payment_safe_write=True).write({"payos_transferred_at": locked_moment})
        locked_tx.with_context(payment_safe_write=True)._set_done()
        locked = reconciliation_days.create({"day": reconciliation_days._vietnam_day(locked_moment)})
        locked.action_post_missing_payments()
        locked.action_lock()
        open_tx = self.env[MODEL_TRANSACTION]._create_payos_transaction(open_invoice)
        open_tx.with_context(payment_safe_write=True).write({"payos_transferred_at": now})
        open_tx.with_context(payment_safe_write=True)._set_done()
        opened = reconciliation_days.create({"day": reconciliation_days._vietnam_day(now)})
        self._remember(
            {
                "demo_reconciliation_day_locked": locked,
                "demo_reconciliation_day_open": opened,
                "demo_account_move_payos_locked": locked_invoice,
                "demo_account_move_payos_open": open_invoice,
            }
        )

    def _demo_portal_users(self, an_phu, green):
        portal = self.env.ref("base.group_portal")
        for xml_id, partner, login in (
            ("demo_res_users_an_phu", an_phu, "portal.anphu"),
            ("demo_res_users_green_farm", green, "portal.greenfarm"),
        ):
            user = self.env["res.users"].create(
                {
                    "name": partner.name,
                    "login": login,
                    "partner_id": partner.id,
                    "group_ids": [Command.set(portal.ids)],
                }
            )
            self._remember({xml_id: user})

    def _demo_notification_rows(self):
        message = self.env["mail.message"].search([("notification_key", "!=", False)], limit=1)
        if not message:
            return
        notification = message.notification_ids[:1]
        if notification:
            notification.is_read = True
        device = self.env.ref("sol_demo.demo_mobile_device_active", raise_if_not_found=False)
        if notification and device:
            self.env["medilab.push.delivery"].sudo().create(
                [
                    {"notification_id": notification.id, "mobile_device_id": device.id, "status": "sent"},
                    {
                        "notification_id": notification.id,
                        "mobile_device_id": self.env.ref("sol_demo.demo_mobile_device_off").id,
                        "status": "skipped",
                    },
                ]
            )

    def _seed_two_rate_invoice(self):
        if self.env.ref("sol_demo.demo_account_move_two_rates", raise_if_not_found=False):
            return
        partner = self.env.ref(PARTNER_AN_PHU, raise_if_not_found=False)
        if not partner:
            return
        product = self.env[MODEL_PRODUCT].create(
            {"name": "Two-rate sample", "type": "service", "list_price": 1_000_000, "invoice_policy": "order"}
        )
        vat8 = self._demo_tax(VAT_EIGHT, 8)
        vat10 = self._demo_tax("VAT 10%", 10)
        invoice = self.create(
            {
                "move_type": "out_invoice",
                "invoice_kind": "final",
                "partner_id": partner.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "quantity": 1,
                            "price_unit": 1_000_000,
                            "tax_ids": [Command.set(vat8.ids)],
                        }
                    ),
                    Command.create(
                        {
                            "product_id": product.id,
                            "quantity": 1,
                            "price_unit": 2_000_000,
                            "tax_ids": [Command.set(vat10.ids)],
                        }
                    ),
                ],
            }
        )
        invoice.action_post()
        self._remember({"demo_account_move_two_rates": invoice})

    def _seed_payos_advance(self):
        if self.env.ref("sol_demo.demo_account_move_payos_advance", raise_if_not_found=False):
            return
        provider = self.env.ref("sol_commerce.payment_provider_payos", raise_if_not_found=False)
        partner = self.env.ref(PARTNER_AN_PHU, raise_if_not_found=False)
        if not provider or not partner:
            return
        provider.is_published = True
        method = self.env.ref("sol_commerce.payment_method_payos_qr", raise_if_not_found=False)
        if method:
            method.active = True
        product = self.env[MODEL_PRODUCT].search([("name", "=", LEAD_IN_WATER)], limit=1)
        tax = self._demo_tax(VAT_EIGHT, 8)
        if not product:
            product = self.env[MODEL_PRODUCT].create(
                {"name": LEAD_IN_WATER, "type": "service", "list_price": 5_000_000, "invoice_policy": "order"}
            )
        order = self._demo_order(partner, product, tax)
        invoice = order.create_advance_invoice(amount=1_000_000)
        transaction = self.env[MODEL_TRANSACTION]._create_payos_transaction(invoice)
        moment = fields.Datetime.to_datetime("2020-01-04 03:00:00")
        transaction.with_context(payment_safe_write=True).write(
            {"payos_transferred_at": moment, "payos_bank_reference": "DEMO-ADVANCE-1"}
        )
        transaction.with_context(payment_safe_write=True)._set_done()
        payment = transaction._create_online_payment()
        self._remember(
            {
                "demo_account_move_payos_advance": invoice,
                "demo_payment_transaction_payos_advance": transaction,
                "demo_account_payment_payos_advance": payment,
            }
        )

    def _seed_failed_push(self):
        if self.env.ref("sol_demo.demo_push_delivery_failed", raise_if_not_found=False):
            return
        notification = self.env["mail.notification"].search([], limit=1)
        device = self.env.ref("sol_demo.demo_mobile_device_failed", raise_if_not_found=False)
        if not notification or not device:
            return
        delivery = (
            self.env["medilab.push.delivery"]
            .sudo()
            .create(
                {
                    "notification_id": notification.id,
                    "mobile_device_id": device.id,
                    "status": "failed",
                    "error": "The push service did not accept the message.",
                }
            )
        )
        self._remember({"demo_push_delivery_failed": delivery})

    def _demo_tax(self, name, amount):
        tax = self.env[MODEL_TAX].search(
            [("name", "=", name), ("amount", "=", amount), ("type_tax_use", "=", "sale")], limit=1
        )
        if tax:
            return tax
        return self.env[MODEL_TAX].create(
            {
                "name": name,
                "amount": amount,
                "amount_type": "percent",
                "type_tax_use": "sale",
                "price_include_override": "tax_excluded",
            }
        )

    def _remember(self, records):
        self.env["ir.model.data"]._update_xmlids(
            [{"xml_id": f"sol_demo.{xml_id}", "record": record, "noupdate": True} for xml_id, record in records.items()]
        )
