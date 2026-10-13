from odoo.tests import tagged

from .audit_case import AuditCase
from odoo.addons.sol_laboratory.constants.models import MODEL_CHEMICAL, MODEL_MOBILE_DEVICE


@tagged("post_install", "-at_install")
class TestAuditMasking(AuditCase):
    def test_a_masked_field_records_that_it_changed_without_its_values(self):
        field = self.env[MODEL_CHEMICAL]._fields["cas_number"]
        field.audit_mask = True
        self.addCleanup(delattr, field, "audit_mask")
        chemical = self.env[MODEL_CHEMICAL].create({"code": "HC-101", "name": "Acetonitrile", "cas_number": "75-05-8"})

        chemical.cas_number = "75-05-9"

        self.assertEqual(self.changes(self.entries(chemical, "create"))["cas_number"], (False, "***"))
        self.assertEqual(self.changes(self.entries(chemical, "edit")), {"cas_number": ("***", "***")})

    def test_odoos_secret_is_masked(self):
        parameters = self.env["ir.config_parameter"].sudo()
        parameters.set_str("database.secret", "a-new-secret")

        parameter = parameters.search([("key", "=", "database.secret")])
        self.assertEqual(self.changes(self.entries(parameter, "edit"))["value"][1], "***")

    def test_a_device_token_is_masked_and_refreshing_it_is_not_a_change(self):
        devices = self.env[MODEL_MOBILE_DEVICE].with_user(self.editor)
        device = devices.register_token("fcm-token-1", "android")

        devices.register_token("fcm-token-1", "android")

        changes = self.changes(self.entries(device, "create"))
        self.assertEqual(changes["token"], (False, "***"))
        self.assertNotIn("last_seen_at", changes)
        self.assertFalse(self.entries(device, "edit"))
