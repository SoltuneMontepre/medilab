from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB


@tagged("post_install", "-at_install")
class TestPaymentRequestReviews(OrderCase):
    def setUp(self):
        super().setUp()
        self.env.ref("sol_commerce.payment_provider_payos").is_published = True
        self.env.ref("sol_commerce.payment_method_payos_qr").active = True

    def _record_payos_transfer(self, link, amount, reference):
        return (
            self.env["payment.transaction"]
            ._payos_apply_webhook(
                {
                    "code": "00",
                    "orderCode": int(link.reference),
                    "amount": amount,
                    "reference": reference,
                    "transactionDateTime": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            .payment_id
        )

    def _late_payos_payment(self, order):
        request = order.payment_request_id
        link = self.env["payment.transaction"]._portal_start_request_payos(request)
        order.payment_deadline = fields.Datetime.now() - timedelta(hours=1)
        return self._record_payos_transfer(link, 1000, "FT-REVIEW-LATE")

    def test_portal_rejects_another_transfer_report_until_review(self):
        order = self.sent_order()
        request = order.payment_request_id
        payments = self.env["account.payment"].with_user(self.portal)
        first = payments._portal_pay_request(request, 1000, reference="FT-FIRST")

        with self.assertRaisesRegex(UserError, "already pending"):
            payments._portal_pay_request(request, 2000, reference="FT-SECOND")

        self.assertEqual(request.payment_ids, first)
        self.assertEqual(first.memo, "FT-FIRST")
        first.action_post()
        second = payments._portal_pay_request(request, 2000, reference="FT-SECOND")
        second.rejection_reason = "No matching transfer"
        second.action_reject_payment()
        third = payments._portal_pay_request(request, 3000, reference="FT-THIRD")
        self.assertEqual(third.memo, "FT-THIRD")
        self.assertEqual(third.amount, 3000)

    def test_payos_draft_blocks_order_changes_without_increasing_pending_amount(self):
        order = self.sent_order()
        payment = self._late_payos_payment(order)
        self.assertEqual(payment.state, "draft")
        self.assertEqual(payment.collection_review, "late")
        self.assertEqual(order.pending_amount, 0)
        self.assertEqual(order.payment_request_id.pending_amount, 0)

        with self.assertRaisesRegex(UserError, "pending payment"):
            order._latest_quotation().with_user(self.portal).sudo().action_decline("Changed our mind")
        with self.assertRaisesRegex(UserError, "pending payment"):
            order.with_user(self.sales).action_sales_cancel()
        order.with_user(self.sales).action_revise_quotation()
        with self.assertRaisesRegex(UserError, "pending payment"):
            order.with_user(self.sales).action_send_quotation()

    def test_payos_receipt_time_cannot_be_backdated(self):
        order = self.sent_order()
        payment = self._late_payos_payment(order)
        actual_time = payment.received_at

        with self.assertRaisesRegex(UserError, "receipt time"):
            payment.write({"received_at": fields.Datetime.now() - timedelta(days=1)})

        self.assertEqual(payment.received_at, actual_time)
        with self.assertRaisesRegex(UserError, "extend the payment deadline"):
            payment.action_post()

    def test_terminal_payos_links_with_partial_payment_can_be_replaced(self):
        transactions = self.env["payment.transaction"]
        for status in ("CANCELLED", "EXPIRED"):
            with self.subTest(status=status):
                request = self.sent_order().payment_request_id
                link = transactions._portal_start_request_payos(request)
                payment = self._record_payos_transfer(link, 1000, f"FT-REVIEW-{status}")
                self.assertEqual(link.state, "done")
                self.assertFalse(link.payos_link_closed)
                item = self.env[MODEL_SCHEDULED_JOB].queue("payos.poll", f"review:{link.reference}", document=link)

                with patch("odoo.addons.sol_commerce.models.invoicing.scheduled_job.payos_client_from_env") as client:
                    client.return_value.request.return_value = {"data": {"status": status, "transactions": []}}
                    self.assertIsNone(item.job_id._handle_payos_poll(item))

                self.assertTrue(link.payos_link_closed)
                self.assertEqual(link.state, "done")
                self.assertEqual(link.payment_id, payment)
                self.assertEqual(request.verified_amount, 1000)
                replacement = transactions._portal_start_request_payos(request)
                self.assertNotEqual(replacement, link)
                self.assertEqual(replacement.amount, request.remaining_amount)
