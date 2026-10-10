import os
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .payos_case import (
    CREATE_PATH,
    GET_PATH,
    JOB_LOGGER,
    LINK_LOGGER,
    PayosCase,
    link_data,
    refusal,
    signed_answer,
    transaction,
)
from odoo.addons.commerce.constants.models import MODEL_PAYMENT_LINK
from odoo.addons.commerce.constants.payos import JOB_CALLS, JOB_POLL, RETURN_ROUTE
from odoo.addons.commerce.services.payos_client import PayosUnavailable
from odoo.addons.laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS, MODEL_SCHEDULED_JOB

CANCEL_PATH = ("POST", "/v2/payment-requests/")
NO_CREDENTIALS = {"PAYOS_CLIENT_ID": "", "PAYOS_API_KEY": "", "PAYOS_CHECKSUM_KEY": ""}


def unreachable(method, path, body):
    raise PayosUnavailable("PayOS could not be reached: ConnectTimeout")


@tagged("post_install", "-at_install")
class TestPaymentLink(PayosCase):
    def settings(self):
        return self.env[MODEL_RES_CONFIG_SETTINGS]

    def test_a_link_is_created_pending_from_what_payos_returns(self):
        invoice = self.create_invoice()

        link, fake = self.create_link(invoice)

        self.assertEqual(link.status, "pending")
        self.assertEqual(link.amount, invoice.amount_owed)
        self.assertEqual(link.checkout_url, "https://pay.payos.vn/web/payoslink0001")
        self.assertEqual(link.provider_payment_link_id, "payoslink0001")
        self.assertGreater(link.provider_order_code, 0)
        self.assertAlmostEqual(link.expires_at, self.hours_from_now(72), delta=timedelta(minutes=1))
        self.assertEqual(self.job_items(JOB_POLL, "pending").mapped("item_key"), [f"poll:{link.id}"])
        method, path, body = fake.calls[0]
        self.assertEqual((method, path), CREATE_PATH)
        self.assertEqual(body["orderCode"], link.provider_order_code)
        self.assertEqual(body["amount"], int(invoice.amount_owed))
        self.assertEqual(body["description"], self.env[MODEL_PAYMENT_LINK]._description_for(invoice))
        self.assertEqual(
            body["expiredAt"], int((link.expires_at - fields.Datetime.from_string("1970-01-01")).total_seconds())
        )
        self.assertTrue(body["returnUrl"].endswith(RETURN_ROUTE))

    def test_the_invoice_button_asks_for_the_owed_amount(self):
        invoice = self.create_invoice()
        self.fake_payos(
            {
                CREATE_PATH: lambda m, p, b: signed_answer(
                    {
                        "orderCode": b["orderCode"],
                        "status": "PENDING",
                        "paymentLinkId": "x",
                        "checkoutUrl": "https://pay.payos.vn/web/x",
                    }
                )
            }
        )

        action = invoice.with_user(self.accountant.user_id).action_create_payment_link()

        link = self.env[MODEL_PAYMENT_LINK].browse(action["res_id"])
        self.assertEqual(
            (action["res_model"], link.invoice_id, link.amount), (MODEL_PAYMENT_LINK, invoice, invoice.amount_owed)
        )
        self.assertEqual(invoice.payment_link_ids, link)

    def test_the_description_keeps_the_number_and_year_of_the_code(self):
        links = self.env[MODEL_PAYMENT_LINK]
        for code, expected in (
            ("0001 26/HD", "000126HD"),
            ("HDVTT0001 26", "000126HDV"),
            ("0042 26/HD-VTT", "004226HDV"),
        ):
            with self.subTest(code=code):
                description = links._description_for(
                    self.env["res.partner"]
                    .new({"name": "x"})
                    .__class__.new(self.env["medilab.invoice"], {"code": code})
                )
                self.assertEqual(description, expected)
                self.assertTrue(description.isalnum() and len(description) <= 9)

    def test_the_expiry_comes_from_the_setting(self):
        self.settings().create({"payos_link_expiry_hours": 24}).set_values()

        link, _ = self.create_link()

        self.assertAlmostEqual(link.expires_at, self.hours_from_now(24), delta=timedelta(minutes=1))

    def test_the_integration_off_refuses(self):
        self.settings().create({"payos_enabled": False}).set_values()
        fake = self.fake_payos()

        with self.assertRaisesRegex(UserError, "turned off"):
            self.create_link(answers={})
        self.assertFalse(fake.calls)
        self.assertFalse(self.job_items(JOB_CALLS))

    def test_missing_credentials_refuse_with_the_message_and_queue_nothing(self):
        with patch.dict(os.environ, NO_CREDENTIALS), self.assertRaisesRegex(UserError, "PAYOS_CLIENT_ID"):
            self.create_link(answers={})
        self.assertFalse(self.job_items(JOB_CALLS))
        self.assertFalse(self.env[MODEL_PAYMENT_LINK].search([("partner_id", "=", self.customer.id)]))

    def test_a_salesperson_cannot_create_a_link(self):
        with self.assertRaises(AccessError):
            self.create_link(user=self.salesperson, answers={})

    def test_the_amount_is_positive_and_at_most_the_owed_amount(self):
        invoice = self.create_invoice()
        for amount in (0, -1, invoice.amount_owed + 1):
            with self.subTest(amount=amount), self.assertRaisesRegex(UserError, "at most what is still owed"):
                self.create_link(invoice, amount=amount, answers={})

    def test_only_a_posted_advance_or_final_invoice_takes_a_link(self):
        draft = self.create_invoice(post=False)
        posted = self.create_invoice()
        adjustment = self.create_invoice(lines=((100_000, 8),), kind="adjustment", adjusts_id=posted.id)
        for invoice in (draft, adjustment):
            with self.subTest(invoice=invoice.kind), self.assertRaisesRegex(UserError, "posted advance or final"):
                self.create_link(invoice, amount=100_000, answers={})

    def test_an_outage_queues_the_creation_and_the_job_completes_it(self):
        with mute_logger(LINK_LOGGER):
            link, fake = self.create_link(answers={CREATE_PATH: unreachable})

        self.assertEqual((link.status, link.checkout_url), ("created", False))
        item = self.job_items(JOB_CALLS)
        self.assertEqual(
            (item.item_key, item.payload, item.status), (f"create:{link.id}", {"call": "create"}, "pending")
        )
        self.assertFalse(self.job_items(JOB_POLL))

        fake.answers[CREATE_PATH] = lambda m, p, b: signed_answer(
            {
                "orderCode": b["orderCode"],
                "status": "PENDING",
                "paymentLinkId": "late",
                "checkoutUrl": "https://pay.payos.vn/web/late",
            }
        )
        self.run_job(JOB_CALLS)

        self.assertEqual(
            (link.status, link.checkout_url, item.status), ("pending", "https://pay.payos.vn/web/late", "done")
        )
        self.assertEqual(self.job_items(JOB_POLL).mapped("item_key"), [f"poll:{link.id}"])

    def test_without_credentials_the_job_calls_nothing_and_retries(self):
        with mute_logger(LINK_LOGGER):
            link, fake = self.create_link(answers={CREATE_PATH: unreachable})
        calls = len(fake.calls)

        with patch.dict(os.environ, NO_CREDENTIALS), mute_logger(JOB_LOGGER):
            self.run_job(JOB_CALLS)

        item = self.job_items(JOB_CALLS)
        self.assertEqual((item.status, item.attempts, len(fake.calls)), ("pending", 1, calls))
        self.assertIn("PAYOS_CLIENT_ID", item.last_error)
        self.assertEqual(link.status, "created")

    def test_a_replay_adopts_the_link_payos_already_knows_with_the_same_amount(self):
        with mute_logger(LINK_LOGGER):
            link, fake = self.create_link(answers={CREATE_PATH: unreachable})
        fake.answers[CREATE_PATH] = refusal()
        fake.answers[GET_PATH] = signed_answer({**link_data(link), "id": "known"})

        self.run_job(JOB_CALLS)

        self.assertEqual(link.status, "pending")
        self.assertEqual(
            (link.provider_payment_link_id, link.checkout_url), ("known", "https://pay.payos.vn/web/known")
        )
        self.assertEqual(self.job_items(JOB_CALLS).status, "done")
        self.assertEqual(fake.paths()[1:], [CREATE_PATH, ("GET", f"/v2/payment-requests/{link.provider_order_code}")])

    def test_a_replay_with_another_amount_fails_at_once(self):
        with mute_logger(LINK_LOGGER):
            link, fake = self.create_link(answers={CREATE_PATH: unreachable})
        fake.answers[CREATE_PATH] = refusal()
        fake.answers[GET_PATH] = signed_answer(link_data(link, amount=link.amount + 1))

        with (
            patch.object(type(self.env[MODEL_SCHEDULED_JOB]), "_notify_failed_item", autospec=True) as notify,
            mute_logger(JOB_LOGGER),
        ):
            self.run_job(JOB_CALLS)

        item = self.job_items(JOB_CALLS)
        self.assertEqual((item.status, item.attempts), ("failed", 1))
        self.assertIn("exists at PayOS with the amount", item.last_error)
        self.assertEqual(link.status, "created")
        notify.assert_called_once()

    def test_a_replay_unknown_at_payos_is_retried(self):
        with mute_logger(LINK_LOGGER):
            link, fake = self.create_link(answers={CREATE_PATH: unreachable})
        fake.answers[CREATE_PATH] = refusal("Dữ liệu không hợp lệ", code="20")
        fake.answers[GET_PATH] = refusal("Mã thanh toán không tồn tại", code="101")

        with mute_logger(JOB_LOGGER):
            self.run_job(JOB_CALLS)

        item = self.job_items(JOB_CALLS)
        self.assertEqual((item.status, item.attempts), ("pending", 1))
        self.assertIn("Dữ liệu không hợp lệ", item.last_error)
        self.assertEqual(link.status, "created")

    def test_a_manual_cancel_is_synchronous_with_a_queued_fallback(self):
        link, fake = self.create_link()
        fake.answers[CANCEL_PATH] = lambda m, p, b: signed_answer(link_data(link, status="CANCELLED"))
        link.with_user(self.accountant.user_id).action_cancel()
        self.assertEqual(link.status, "cancelled")
        self.assertEqual(fake.paths()[-1], ("POST", f"/v2/payment-requests/{link.provider_order_code}/cancel"))

        other, fake = self.create_link()
        fake.answers[CANCEL_PATH] = unreachable
        with mute_logger(LINK_LOGGER):
            other.with_user(self.accountant.user_id).action_cancel()
        item = self.job_items(JOB_CALLS, "pending")
        self.assertEqual((other.status, item.item_key), ("cancelled", f"cancel:{other.id}"))

        fake.answers[CANCEL_PATH] = lambda m, p, b: signed_answer(link_data(other, status="CANCELLED"))
        self.run_job(JOB_CALLS)
        self.assertEqual(item.status, "done")

    def test_cancelling_a_link_never_created_at_payos_drops_the_queued_creation(self):
        with mute_logger(LINK_LOGGER):
            link, fake = self.create_link(answers={CREATE_PATH: unreachable})
        item = self.job_items(JOB_CALLS)
        calls_before = len(fake.calls)

        link.with_user(self.accountant.user_id).action_cancel()

        self.assertEqual((link.status, item.status), ("cancelled", "cancelled"))
        self.assertEqual(len(fake.calls), calls_before)

    def test_a_final_link_cannot_be_cancelled_and_a_reader_cannot_cancel(self):
        link, _ = self.create_link()
        self.grant(self.salesperson, "payment.link.read.all")
        with self.assertRaises(AccessError):
            link.with_user(self.salesperson.user_id).action_cancel()
        self.assertEqual(link.with_user(self.salesperson.user_id).status, "pending")

        link._apply_provider_update([], "PAID")
        with self.assertRaisesRegex(UserError, "already paid"):
            link.with_user(self.accountant.user_id).action_cancel()

    def test_the_status_moves_forward_only_and_paid_wins_over_local_closures(self):
        link, _ = self.create_link()
        link._advance_status("expired")
        link._apply_provider_update([transaction("FT1", int(link.amount))], "PAID")
        self.assertEqual(link.status, "paid")

        other, _ = self.create_link()
        other._advance_status("cancelled")
        other._apply_provider_update([transaction("FT2", int(other.amount))], "PAID")
        self.assertEqual(other.status, "paid")

        for later in ("CANCELLED", "EXPIRED", "PENDING"):
            other._apply_provider_update([], later)
            self.assertEqual(other.status, "paid", later)

        third, _ = self.create_link()
        third._apply_provider_update([], "EXPIRED")
        third._apply_provider_update([], "PENDING")
        self.assertEqual(third.status, "expired")

    def test_transfers_are_stored_once_with_their_sum_and_their_vietnam_day(self):
        link, _ = self.create_link()
        transfers = [
            transaction("FT1", 1_700_000, "2026-03-03 10:15:00"),
            transaction("FT2", 1_000_000, "2026-03-03 00:30:00"),
        ]

        link._apply_provider_update(transfers, "PAID")
        link._apply_provider_update(transfers, "PAID")

        self.assertEqual(len(link.transaction_ids), 2)
        self.assertEqual(link.amount_paid, 2_700_000)
        first, second = link.transaction_ids.sorted("reference")
        self.assertEqual(first.transacted_at, fields.Datetime.from_string("2026-03-03 03:15:00"))
        self.assertEqual(second.transacted_at, fields.Datetime.from_string("2026-03-02 17:30:00"))
        self.assertEqual(set(link.transaction_ids.mapped("transacted_date")), {fields.Date.from_string("2026-03-03")})

    def test_a_notification_from_payos_is_summed_into_the_status(self):
        link, _ = self.create_link()
        links = self.env[MODEL_PAYMENT_LINK]

        self.assertTrue(
            links._handle_webhook(
                {
                    "orderCode": link.provider_order_code,
                    "code": "00",
                    "reference": "FT1",
                    "amount": 1_000_000,
                    "transactionDateTime": "2026-03-03 10:15:00",
                }
            )
        )
        self.assertEqual((link.status, link.amount_paid), ("pending", 1_000_000))
        self.assertTrue(
            links._handle_webhook(
                {
                    "orderCode": str(link.provider_order_code),
                    "code": "00",
                    "reference": "FT2",
                    "amount": int(link.amount) - 1_000_000,
                    "transactionDateTime": "2026-03-03 11:00:00",
                }
            )
        )
        self.assertEqual((link.status, link.amount_paid), ("paid", link.amount))
        self.assertFalse(links._handle_webhook({"orderCode": 123456, "code": "00", "reference": "FT3", "amount": 1}))
        self.assertTrue(
            links._handle_webhook(
                {"orderCode": link.provider_order_code, "code": "01", "reference": "FT4", "amount": 1}
            )
        )
        self.assertEqual(len(link.transaction_ids), 2)
