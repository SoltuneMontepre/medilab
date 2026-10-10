from datetime import timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tools import mute_logger

from .payos_case import GET_PATH, JOB_LOGGER, PayosCase, link_data, signed_answer, transaction
from odoo.addons.commerce.constants.models import MODEL_PAYMENT_LINK
from odoo.addons.commerce.constants.payos import JOB_POLL
from odoo.addons.commerce.services.payos_client import PayosUnavailable


def unreachable(method, path, body):
    raise PayosUnavailable("PayOS could not be reached: ConnectTimeout")


@tagged("post_install", "-at_install")
class TestPayosPoll(PayosCase):
    def poll_item(self, link):
        return self.job_items(JOB_POLL).filtered(lambda item: item.item_key == f"poll:{link.id}")

    def test_a_missed_notification_is_caught_up_by_the_job(self):
        link, fake = self.create_link()
        fake.answers[GET_PATH] = signed_answer(link_data(link, "PAID", [transaction("FT1", int(link.amount))]))

        self.run_job(JOB_POLL)

        self.assertEqual((link.status, link.amount_paid), ("paid", link.amount))
        self.assertEqual(link.transaction_ids.mapped("reference"), ["FT1"])
        self.assertEqual(self.poll_item(link).status, "done")

    def test_a_transfer_the_webhook_stored_is_not_duplicated(self):
        link, fake = self.create_link()
        self.env[MODEL_PAYMENT_LINK]._handle_webhook(
            {
                "orderCode": link.provider_order_code,
                "code": "00",
                "reference": "FT1",
                "amount": 1_000_000,
                "transactionDateTime": "2026-03-03 10:15:00",
            }
        )
        fake.answers[GET_PATH] = signed_answer(
            link_data(link, "PAID", [transaction("FT1", 1_000_000), transaction("FT2", int(link.amount) - 1_000_000)])
        )

        self.run_job(JOB_POLL)

        self.assertEqual(sorted(link.transaction_ids.mapped("reference")), ["FT1", "FT2"])
        self.assertEqual((link.status, link.amount_paid), ("paid", link.amount))

    def test_a_link_still_pending_is_asked_again_later(self):
        link, fake = self.create_link()
        fake.answers[GET_PATH] = signed_answer(link_data(link, "PENDING"))

        self.run_job(JOB_POLL)

        item = self.poll_item(link)
        self.assertEqual((link.status, item.status, item.attempts), ("pending", "pending", 0))
        self.assertAlmostEqual(
            item.next_attempt_at, fields.Datetime.now() + timedelta(minutes=15), delta=timedelta(minutes=1)
        )

    def test_past_the_expiry_and_its_margin_the_link_expires_and_the_polling_ends(self):
        link, fake = self.create_link()
        link.sudo().write({"expires_at": fields.Datetime.now() - timedelta(hours=2)})
        fake.answers[GET_PATH] = signed_answer(link_data(link, "PENDING"))

        self.run_job(JOB_POLL)

        self.assertEqual((link.status, self.poll_item(link).status), ("expired", "done"))

    def test_a_paid_reported_after_the_local_expiry_still_records_the_money(self):
        link, _ = self.create_link()
        link._advance_status("expired")

        self.env[MODEL_PAYMENT_LINK]._handle_webhook(
            {
                "orderCode": link.provider_order_code,
                "code": "00",
                "reference": "FT1",
                "amount": int(link.amount),
                "transactionDateTime": "2026-03-06 10:15:00",
            }
        )

        self.assertEqual((link.status, link.amount_paid), ("paid", link.amount))

    def test_a_final_link_ends_the_polling_without_a_call(self):
        link, fake = self.create_link()
        link._advance_status("cancelled")
        calls = len(fake.calls)

        self.run_job(JOB_POLL)

        self.assertEqual(self.poll_item(link).status, "done")
        self.assertEqual(len(fake.calls), calls)

    def test_an_outage_retries_the_poll(self):
        link, fake = self.create_link()
        fake.answers[GET_PATH] = unreachable

        with mute_logger(JOB_LOGGER):
            self.run_job(JOB_POLL)

        item = self.poll_item(link)
        self.assertEqual((item.status, item.attempts), ("pending", 1))
        self.assertIn("could not be reached", item.last_error)
