import json
import os
from unittest.mock import patch

from odoo.fields import Command
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from .payos_case import CREDENTIALS, enable_payos, webhook_payload
from odoo.addons.commerce.constants.models import MODEL_INVOICE, MODEL_PAYMENT_LINK
from odoo.addons.commerce.constants.payos import JOB_POLL, WEBHOOK_ROUTE
from odoo.addons.commerce.services.payos_client import sign
from odoo.addons.laboratory.constants.models import MODEL_JOB_ITEM

JSON_HEADERS = {"Content-Type": "application/json"}


@tagged("post_install", "-at_install")
class TestPayosWebhook(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        enable_payos(cls)
        customer = cls.env["res.partner"].create({"name": "Công ty TNHH Thực phẩm Sao Mai"})
        cls.invoice = cls.env[MODEL_INVOICE].create(
            {
                "partner_id": customer.id,
                "line_ids": [Command.create({"description": "Lead (Pb)", "amount_untaxed": 2_500_000, "tax_rate": 8})],
            }
        )
        cls.invoice.action_post()
        cls.link = cls.env[MODEL_PAYMENT_LINK].create(
            {
                "invoice_id": cls.invoice.id,
                "amount": cls.invoice.amount_owed,
                "status": "pending",
                "expires_at": "2099-01-01 00:00:00",
                "provider_payment_link_id": "payoslink0001",
                "checkout_url": "https://pay.payos.vn/web/payoslink0001",
            }
        )

    def notify(self, payload):
        return self.url_open(WEBHOOK_ROUTE, data=json.dumps(payload), headers=JSON_HEADERS)

    def poll_items(self):
        return self.env[MODEL_JOB_ITEM].search([("job_id.key", "=", JOB_POLL), ("document_id", "=", self.link.id)])

    def test_a_wrong_signature_is_refused_and_changes_nothing(self):
        payload = webhook_payload(self.link, 2_700_000, "FT0001", key="another-key")

        with mute_logger("werkzeug"):
            response = self.notify(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"success": False})
        self.link.invalidate_recordset()
        self.assertEqual((self.link.status, len(self.link.transaction_ids)), ("pending", 0))

    def test_without_a_checksum_key_every_notification_is_refused(self):
        payload = webhook_payload(self.link, 2_700_000, "FT0001", key="")

        with patch.dict(os.environ, {"PAYOS_CHECKSUM_KEY": ""}), mute_logger("werkzeug"):
            response = self.notify(payload)

        self.assertEqual(response.status_code, 400)
        self.link.invalidate_recordset()
        self.assertEqual(len(self.link.transaction_ids), 0)

    def test_malformed_json_is_refused(self):
        with mute_logger("werkzeug"):
            response = self.url_open(WEBHOOK_ROUTE, data="{not json", headers=JSON_HEADERS)

        self.assertEqual(response.status_code, 400)

    def test_a_signed_transfer_of_the_full_amount_pays_the_link_once(self):
        payload = webhook_payload(self.link, 2_700_000, "FT0001")

        first = self.notify(payload)
        second = self.notify(payload)

        self.assertEqual((first.status_code, first.json()), (200, {"success": True}))
        self.assertEqual((second.status_code, second.json()), (200, {"success": True}))
        self.link.invalidate_recordset()
        self.assertEqual(self.link.status, "paid")
        self.assertEqual(self.link.transaction_ids.mapped("reference"), ["FT0001"])
        self.assertEqual(self.link.amount_paid, 2_700_000)
        self.assertEqual(len(self.poll_items()), 1)

    def test_a_transfer_below_the_amount_keeps_the_link_pending(self):
        response = self.notify(webhook_payload(self.link, 1_000_000, "FT0002"))

        self.assertEqual(response.status_code, 200)
        self.link.invalidate_recordset()
        self.assertEqual((self.link.status, self.link.amount_paid), ("pending", 1_000_000))
        self.assertEqual(len(self.link.transaction_ids), 1)

    def test_an_unknown_order_code_is_acknowledged(self):
        # PayOS confirms a webhook address with a signed notification for the order code 123.
        payload = webhook_payload(self.link, 3_000, "TF230204212323")
        payload["data"]["orderCode"] = 123
        payload["signature"] = sign(payload["data"], CREDENTIALS["PAYOS_CHECKSUM_KEY"])

        response = self.notify(payload)

        self.assertEqual((response.status_code, response.json()), (200, {"success": True}))
        self.assertFalse(self.env[MODEL_PAYMENT_LINK].search([("provider_order_code", "=", 123)]))

    def test_a_failed_notification_records_nothing(self):
        response = self.notify(webhook_payload(self.link, 2_700_000, "FT0003", code="01"))

        self.assertEqual(response.status_code, 200)
        self.link.invalidate_recordset()
        self.assertEqual((self.link.status, len(self.link.transaction_ids)), ("pending", 0))
