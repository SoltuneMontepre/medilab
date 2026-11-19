from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged

from .invoicing_case import post_legacy_advance_invoice
from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_QUOTATION
from odoo.addons.sol_commerce.constants.notifications import EVENT_QUOTATION_SENT


@tagged("post_install", "-at_install")
class TestQuotationAdvance(OrderCase):
    def as_customer(self, order):
        """The latest quotation as the customer's portal user reaches it on the portal."""
        return order._latest_quotation().with_user(self.portal).sudo()

    def customer_notices(self, order):
        return order.message_ids.filtered(
            lambda message: (
                message.subtype_id.code == EVENT_QUOTATION_SENT
                and message.notification_ids.res_partner_id == self.contact
            )
        )

    def test_sending_with_an_advance_requests_half_without_posting_an_invoice(self):
        order = self.make_quotable_order()
        order.write({"advance_mode": "percentage", "advance_value": 50})

        order.with_user(self.sales).action_send_quotation()

        self.assertFalse(order.invoice_ids)
        request = order.payment_request_id
        self.assertEqual(request.amount, order.currency_id.round(order.amount_total / 2))
        self.assertEqual(request.state, "open")
        notices = self.customer_notices(order)
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices.attachment_ids, order._latest_quotation().attachment_id)
        self.assertEqual(order.order_status, "claimed")

    def test_verifying_transfers_posts_each_advance_and_funds_on_full_amount(self):
        order = self.make_quotable_order()
        order.write({"advance_mode": "percentage", "advance_value": 50})
        order.with_user(self.sales).action_send_quotation()
        request = order.payment_request_id
        first = order.currency_id.round(request.amount / 3)

        self.env["account.payment"]._create_request_payment(request, first, "bank_transfer").action_post()

        self.assertEqual(order.invoice_ids.amount_total, first)
        self.assertEqual(order.invoice_ids.amount_residual, 0)
        self.assertEqual(order._latest_quotation().status, "sent")
        self.assertEqual(request.remaining_amount, request.amount - first)

        self.env["account.payment"]._create_request_payment(request, request.remaining_amount, "cash").action_post()

        self.assertEqual(len(order.invoice_ids), 2)
        self.assertEqual(order._latest_quotation().status, "accepted")
        self.assertEqual(request.state, "funded")
        self.assertEqual(order.payment_status, "partial")

    def test_a_verified_collection_cannot_be_cancelled_or_reset(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        request = order.payment_request_id
        payment = self.env["account.payment"]._create_request_payment(request, request.amount, "cash")
        payment.action_post()

        for reverse in (
            payment.action_cancel,
            payment.action_draft,
            payment.unlink,
            payment.move_id.button_cancel,
            payment.move_id.button_draft,
        ):
            with self.assertRaisesRegex(UserError, "verified payment request collection"), self.env.cr.savepoint():
                reverse()

        self.assertEqual(request.state, "funded")
        self.assertEqual(request.remaining_amount, 0)
        self.assertEqual(order._latest_quotation().status, "accepted")

    def test_balance_installments_each_bill_the_amount_received(self):
        order = self.make_quotable_order()
        order.write({"advance_mode": "percentage", "advance_value": 50})
        order.with_user(self.sales).action_send_quotation()
        advance = order.payment_request_id
        payments = self.env["account.payment"]
        payments._create_request_payment(advance, advance.amount, "cash").action_post()
        order.payment_deadline = fields.Datetime.now() - timedelta(days=1)
        order.with_user(self.sales).action_confirm_order()
        balance = order.payment_request_id
        self.assertEqual(balance.kind, "balance")
        self.assertEqual(balance.amount, order.amount_total - advance.amount)
        self.assertFalse(balance.deadline)
        with self.assertRaisesRegex(ValidationError, "Balance payment requests have no deadline"):
            balance.write({"deadline": advance.deadline})

        first = order.currency_id.round(balance.amount / 3)
        payments._create_request_payment(balance, first, "cash").action_post()
        self.assertEqual(order.test_request_id.status, "confirmed")
        balance._expire_requests()
        self.assertEqual(balance.state, "open")
        self.assertEqual(balance.verified_amount, first)
        payments._create_request_payment(balance, balance.remaining_amount, "bank_transfer").action_post()

        final_invoices = order.invoice_ids.filtered(lambda invoice: invoice.invoice_kind == "final")
        self.assertCountEqual(final_invoices.mapped("amount_total"), (first, balance.amount - first))
        self.assertEqual(order.test_request_id.status, "paid")
        self.assertEqual(order.payment_status, "paid")

    def test_the_closing_balance_invoice_keeps_the_quoted_tax(self):
        order = self.make_quotable_order()
        taxes = order._catalog_lines().tax_ids
        self.assertTrue(taxes)
        order.write({"advance_mode": "percentage", "advance_value": 50})
        order.with_user(self.sales).action_send_quotation()
        self.pay_advance(order)
        order.with_user(self.sales).action_confirm_order()
        balance = order.payment_request_id
        payment = self.env["account.payment"]._create_request_payment(balance, balance.amount, "cash")

        with self.assertRaisesRegex(UserError, "Only a claimed order can be revised"):
            order.with_user(self.sales).action_revise_quotation()
        with self.assertRaisesRegex(UserError, "revise it before changing its lines"):
            order._catalog_lines().write({"tax_ids": [Command.clear()]})

        payment.action_post()

        invoice = order.invoice_ids.filtered(lambda move: move.payment_request_id == balance)
        self.assertEqual(invoice.invoice_line_ids.tax_ids, taxes)
        self.assertEqual(invoice.amount_total, balance.amount)

    def test_a_preexisting_advance_invoice_still_controls_acceptance(self):
        order = self.make_quotable_order()
        invoice = post_legacy_advance_invoice(order, percentage=50)
        order.with_user(self.sales).action_send_quotation()
        quotation = order._latest_quotation()
        request = order.payment_request_id
        order.payment_request_id = False
        request.unlink()
        quotation.write({"advance_invoice_id": invoice.id})

        with self.assertRaisesRegex(UserError, "Pay the requested advance"):
            self.as_customer(order).action_accept()
        self.env["account.payment"].create_pending_payment(invoice, invoice.amount_total, "cash").action_post()
        self.assertEqual(quotation.status, "accepted")
        order.with_user(self.sales).action_confirm_order()
        self.assertEqual(order.payment_request_id.amount, order.amount_total - invoice.amount_total)

    def test_sales_open_an_order_that_has_an_advance_invoice(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        self.pay_advance(order)

        for user in (self.sales, self.head):
            order.invalidate_recordset()
            values = order.with_user(user).read(["invoice_count", "payment_status"])[0]
            self.assertEqual(values["invoice_count"], 1)
            self.assertEqual(values["payment_status"], "paid")
        self.assertFalse(order.sudo().invoice_ids.with_user(self.other_sales).has_access("read"))

    def test_the_advance_follows_the_percentage_and_the_fixed_amount(self):
        percentage = self.make_quotable_order()
        percentage.write({"advance_mode": "percentage", "advance_value": 30})
        fixed = self.make_quotable_order()
        fixed.write({"advance_mode": "fixed", "advance_value": 50000})

        percentage.with_user(self.sales).action_send_quotation()
        fixed.with_user(self.sales).action_send_quotation()

        self.assertAlmostEqual(
            percentage.payment_request_id.amount, percentage.currency_id.round(percentage.amount_total * 0.3)
        )
        self.assertAlmostEqual(fixed.payment_request_id.amount, 50000)

    def test_an_advance_needs_a_method_and_a_value(self):
        order = self.make_quotable_order()
        order.advance_method = False
        with self.assertRaises(UserError):
            order.with_user(self.sales).action_send_quotation()
        order.write({"advance_method": "cash", "advance_mode": "percentage", "advance_value": 0})
        with self.assertRaises(UserError):
            order.with_user(self.sales).action_send_quotation()
        order.advance_value = 101
        with self.assertRaises(UserError):
            order.with_user(self.sales).action_send_quotation()

        self.assertFalse(order.quotation_ids)
        self.assertFalse(order.sudo().invoice_ids)

    def test_sending_a_second_time_does_not_create_a_second_request(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_send_quotation()

        self.assertEqual(len(order.payment_request_ids), 1)
        self.assertEqual(len(self.customer_notices(order)), 1)

    def test_only_the_head_of_sales_sends_without_an_advance(self):
        order = self.make_quotable_order()
        order.advance_method = "none"

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_send_quotation()
        self.assertFalse(order.quotation_ids)

        order.with_user(self.head).action_send_quotation()

        self.assertEqual(order._latest_quotation().status, "sent")
        self.assertFalse(order.sudo().invoice_ids)
        self.assertEqual(len(self.customer_notices(order)), 1)

    def test_paying_the_advance_accepts_the_quotation(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        self.assertEqual(order.quotation_follow_up, "unpaid")
        self.assertEqual(order.payment_status, "not_paid")

        self.pay_advance(order)

        invoice = order.invoice_ids
        self.assertEqual(invoice.invoice_kind, "advance")
        self.assertEqual(invoice.order_id, order)
        self.assertEqual(order._latest_quotation().status, "accepted")
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.quotation_follow_up, "paid")
        self.assertFalse(order.show_unpaid_warning)

    def test_the_customer_accepts_a_quotation_sent_without_an_advance(self):
        order = self.make_quotable_order()
        order.advance_method = "none"
        order.with_user(self.head).action_send_quotation()

        self.as_customer(order).action_accept()

        self.assertEqual(order._latest_quotation().status, "accepted")
        self.assertEqual(order.quotation_follow_up, "accepted")
        self.assertFalse(order.show_unpaid_warning)

    def test_only_a_quotation_without_an_advance_is_accepted_by_the_customer(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()

        with self.assertRaises(UserError):
            self.as_customer(order).action_accept()

        self.assertEqual(order._latest_quotation().status, "sent")

    def test_a_salesperson_cannot_accept_for_the_customer(self):
        order = self.make_quotable_order()
        order.advance_method = "none"
        order.with_user(self.head).action_send_quotation()
        quotation = order._latest_quotation()

        for caller in (quotation.with_user(self.sales), quotation.with_user(self.head), quotation):
            with self.assertRaises(AccessError):
                caller.action_accept()

        self.assertEqual(quotation.status, "sent")

    def test_pending_transfer_blocks_sending_declining_and_cancelling_but_allows_drafting(self):
        order = self.sent_order()
        received = order.with_user(self.sales).action_record_collection(1000, "bank_transfer", reference="FT-DRAFT")
        payment = self.env["account.payment"].browse(received)
        self.assertEqual(order.pending_amount, 1000)
        self.assertFalse(order.invoice_ids)
        with self.assertRaisesRegex(UserError, "pending payment"):
            self.as_customer(order).action_decline("Changed our mind")
        with self.assertRaisesRegex(UserError, "pending payment"):
            order.with_user(self.sales).action_sales_cancel()
        with self.assertRaises(AccessError):
            payment.with_user(self.sales).action_post()

        order.with_user(self.sales).action_revise_quotation()
        self.assertEqual(order.state, "draft")
        with self.assertRaisesRegex(UserError, "pending payment"):
            order.with_user(self.sales).action_send_quotation()
        self.assertEqual(order._latest_quotation().revision, 1)

        payment.rejection_reason = "No matching bank transfer"
        payment.action_reject_payment()
        self.assertEqual(order.pending_amount, 0)
        order.with_user(self.sales).action_send_quotation()
        self.assertEqual(order._latest_quotation().revision, 2)
        self.assertFalse(order.invoice_ids)

    def test_payment_received_on_time_funds_expired_quotation_on_later_verification(self):
        order = self.sent_order()
        deadline = fields.Datetime.now() - timedelta(hours=1)
        order.payment_deadline = deadline
        payment_id = order.with_user(self.sales).action_record_collection(
            order.amount_total, "bank_transfer", received_at=deadline - timedelta(minutes=5), reference="FT-TIMELY"
        )
        self.env[MODEL_QUOTATION]._flag_expired()
        self.assertEqual(order.payment_request_id.state, "expired")
        self.assertEqual(order._latest_quotation().status, "expired")

        self.env["account.payment"].browse(payment_id).action_post()

        self.assertEqual(order.payment_request_id.state, "funded")
        self.assertEqual(order._latest_quotation().status, "accepted")

    def test_payment_received_after_deadline_waits_for_sales_to_extend_it(self):
        order = self.sent_order()
        order.payment_deadline = fields.Datetime.now() - timedelta(hours=1)
        self.env[MODEL_QUOTATION]._flag_expired()
        payment_id = order.with_user(self.sales).action_record_collection(order.amount_total, "cash")
        payment = self.env["account.payment"].browse(payment_id)

        with self.assertRaisesRegex(UserError, "extend the payment deadline"):
            payment.action_post()
        self.assertEqual(payment.state, "draft")
        self.assertFalse(order.invoice_ids)

        order.with_user(self.sales).payment_deadline = fields.Datetime.now() + timedelta(days=1)
        payment.action_post()

        self.assertEqual(order._latest_quotation().status, "accepted")

    def test_expiry_keeps_part_payment_and_closes_the_published_link(self):
        order = self.sent_order()
        request = order.payment_request_id
        payment = self.env["account.payment"]._create_request_payment(request, 1000, "cash")
        payment.action_post()
        self.env.ref("sol_commerce.payment_provider_payos").is_published = True
        link = self.env["payment.transaction"]._create_payos_transaction(request, request.remaining_amount)
        order.payment_deadline = fields.Datetime.now() - timedelta(hours=1)

        self.env[MODEL_QUOTATION]._flag_expired()

        self.assertEqual(request.state, "expired")
        self.assertEqual(request.verified_amount, 1000)
        self.assertEqual(link.state, "cancel")
        self.assertTrue(link.payos_link_closed)
        self.assertEqual(payment.invoice_ids.state, "posted")
        self.assertFalse(payment.invoice_ids.is_overdue)
        self.assertEqual(order.order_status, "claimed")
        with self.assertRaises(UserError):
            self.env["account.payment"]._portal_pay_request(request, 1)

    def test_payos_completion_posts_one_invoice_for_each_transfer(self):
        order = self.sent_order()
        request = order.payment_request_id
        part = order.currency_id.round(request.amount / 3)
        self.env["account.payment"]._create_request_payment(request, part, "bank_transfer").action_post()
        transactions = self.env["payment.transaction"]
        self.env.ref("sol_commerce.payment_provider_payos").is_published = True
        link = transactions._create_payos_transaction(request, request.remaining_amount)
        data = self._payos_transfer(link, "FT-ADVANCE-582")

        transactions._payos_apply_webhook(data)
        transactions._payos_apply_webhook(data)

        self.assertEqual(len(order.invoice_ids), 2)
        self.assertEqual(len(request.payment_ids), 2)
        self.assertCountEqual(order.invoice_ids.mapped("amount_total"), [part, request.amount - part])
        self.assertEqual(request.state, "funded")
        self.assertEqual(order._latest_quotation().status, "accepted")

    def test_transfer_to_a_superseded_link_waits_for_accountant_review(self):
        order = self.sent_order()
        original = order.payment_request_id
        transactions = self.env["payment.transaction"]
        self.env.ref("sol_commerce.payment_provider_payos").is_published = True
        link = transactions._create_payos_transaction(original, original.amount)
        order.with_user(self.sales).action_revise_quotation()
        order.with_user(self.sales).action_send_quotation()
        self.assertEqual(link.state, "cancel")
        revised = order.payment_request_id
        data = self._payos_transfer(link, "FT-PREVIOUS-582")

        received = transactions._payos_apply_webhook(data)
        transactions._payos_apply_webhook(data)

        payment = received.payment_id
        self.assertEqual(original.payment_ids, payment)
        self.assertEqual(payment.state, "draft")
        self.assertEqual(payment.collection_review, "previous_request")
        self.assertEqual(revised.verified_amount, 0)
        self.assertFalse(order.invoice_ids)
        payment.action_post()
        self.assertEqual(payment.payment_request_id, revised)
        self.assertEqual(revised.state, "funded")
        self.assertEqual(order._latest_quotation().status, "accepted")

    def _payos_transfer(self, link, reference):
        return {
            "code": "00",
            "orderCode": int(link.reference),
            "amount": link.amount,
            "reference": reference,
            "transactionDateTime": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M:%S"),
        }

    def test_funded_revision_reuses_money_but_requires_explicit_agreement(self):
        order = self.sent_order()
        first = order._latest_quotation()
        old_request = order.payment_request_id
        self.pay_advance(order)
        advance = order.invoice_ids
        order.with_user(self.sales).action_revise_quotation()
        order.advance_mode = "percentage"
        order.advance_value = 80
        order.with_user(self.sales).action_send_quotation()
        quotation = order._latest_quotation()

        self.assertEqual(first.status, "replaced")
        self.assertEqual(old_request.state, "superseded")
        self.assertEqual(advance.state, "posted")
        self.assertEqual(order.invoice_ids, advance)
        self.assertEqual(order.payment_request_id.amount, 0)
        self.assertEqual(order.payment_request_id.carried_amount, advance.amount_total)
        self.assertEqual(quotation.status, "sent")

        order.with_user(self.sales).action_record_quotation_agreement("Customer's approval email")
        self.assertEqual(quotation.status, "accepted")
        self.assertEqual(quotation.agreement_reference, "Customer's approval email")

    def test_follow_up_shows_unpaid_paid_declined_and_expired(self):
        unpaid, paid, declined, expired = (self.make_quotable_order() for _ in range(4))
        for order in (unpaid, paid, declined, expired):
            order.with_user(self.sales).action_send_quotation()
        self.pay_advance(paid)
        declined._latest_quotation().action_decline("Too expensive")
        expired.payment_deadline = fields.Datetime.now() - timedelta(days=1)
        self.env[MODEL_QUOTATION]._flag_expired()

        self.assertEqual(
            [order.quotation_follow_up for order in (unpaid, paid, declined, expired)],
            ["unpaid", "paid", "declined", "expired"],
        )

    def test_the_company_does_not_ask_the_customer_to_sign_online(self):
        self.assertFalse(self.env.company.portal_confirmation_sign)
        self.assertFalse(self.make_order([(self.lead_product, 1)]).require_signature)

    def test_a_salesperson_cannot_switch_a_sent_advance_quotation_to_no_advance(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()

        with self.assertRaises(UserError):
            order.with_user(self.sales).write({"advance_method": "none"})

        self.assertEqual(order.advance_method, "cash")
        with self.assertRaises(UserError):
            self.as_customer(order).action_accept()
        self.assertEqual(order._latest_quotation().status, "sent")

    def test_a_quotation_being_revised_cannot_be_accepted(self):
        order = self.make_quotable_order()
        order.advance_method = "none"
        order.with_user(self.head).action_send_quotation()
        order.with_user(self.sales).action_revise_quotation()
        self.assertEqual(order.state, "draft")

        with self.assertRaises(UserError):
            self.as_customer(order).action_accept()

        self.assertEqual(order._latest_quotation().status, "sent")

    def test_accepting_follows_the_request_of_the_sent_quotation(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        order.with_user(self.sales).action_revise_quotation()
        order.with_user(self.sales).write({"advance_method": "none"})
        quotation = order._latest_quotation()
        self.assertTrue(quotation.payment_request_ids)

        with self.assertRaises(UserError):
            self.as_customer(order).action_accept()

        self.assertEqual(quotation.status, "sent")

    def test_the_advance_cannot_change_after_sending_until_the_quotation_is_revised(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()

        for values in ({"advance_method": "none"}, {"advance_mode": "fixed"}, {"advance_value": 5}):
            with self.subTest(values=values):
                with self.assertRaises(UserError):
                    order.write(values)
                with self.assertRaises(UserError):
                    order.with_user(self.sales).write(values)
        self.assertEqual(order.advance_method, "cash")
        with self.assertRaises(UserError):
            self.as_customer(order).action_accept()

        order.with_user(self.sales).action_revise_quotation()
        order.with_user(self.sales).write({"advance_method": "bank_transfer"})

        self.assertEqual(order.advance_method, "bank_transfer")
