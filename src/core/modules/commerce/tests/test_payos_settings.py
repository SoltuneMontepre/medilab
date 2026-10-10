from odoo.exceptions import AccessError
from odoo.tests import tagged

from .invoicing_case import InvoicingCase
from odoo.addons.laboratory.constants.models import MODEL_IR_CONFIG_PARAMETER, MODEL_RES_CONFIG_SETTINGS


@tagged("post_install", "-at_install")
class TestPayosSettings(InvoicingCase):
    def settings(self):
        return self.env[MODEL_RES_CONFIG_SETTINGS]

    def test_the_defaults_apply_when_nothing_is_stored(self):
        self.env[MODEL_IR_CONFIG_PARAMETER].search([("key", "=like", "medilab.commerce.payos_%")]).unlink()

        self.assertIs(self.settings()._get_parameter("payos_enabled"), False)
        self.assertIs(self.settings()._get_parameter("payos_method_qr_transfer"), True)
        self.assertEqual(self.settings()._get_parameter("payos_link_expiry_hours"), 72)
        self.assertEqual(self.settings()._enabled_payment_methods(), ["qr_transfer"])

    def test_a_disabled_method_is_not_offered(self):
        self.settings().create({"payos_enabled": True, "payos_method_qr_transfer": False}).set_values()

        self.assertIs(self.settings()._get_parameter("payos_enabled"), True)
        self.assertEqual(self.settings()._enabled_payment_methods(), [])

    def test_only_administrators_change_the_payos_settings(self):
        with self.assertRaises(AccessError):
            self.settings().with_user(self.accountant.user_id).create({"payos_enabled": True})

    def test_the_block_shows_whether_credentials_are_configured_without_their_values(self):
        from unittest.mock import patch

        from odoo.addons.commerce.services.payos_client import PayosClient

        with patch.dict("os.environ", {"PAYOS_CLIENT_ID": "", "PAYOS_API_KEY": "", "PAYOS_CHECKSUM_KEY": ""}):
            self.assertFalse(self.settings().create({}).payos_configured)
            self.assertFalse(PayosClient().is_configured())
        with patch.dict("os.environ", {"PAYOS_CLIENT_ID": "id", "PAYOS_API_KEY": "key", "PAYOS_CHECKSUM_KEY": "sum"}):
            settings = self.settings().create({})
            self.assertTrue(settings.payos_configured)
            self.assertNotIn("payos_configured", [name for name, _ in settings._get_classified_fields()["config"]])
