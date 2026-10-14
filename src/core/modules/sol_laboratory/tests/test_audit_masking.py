from odoo.fields import Command
from odoo.tests import tagged

from .audit_case import AuditCase
from odoo.addons.sol_laboratory.constants.audit import MASK_PERSONAL, MASK_SECRET
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_CHANGE,
    MODEL_AUDIT_ENTRY,
    MODEL_CHEMICAL,
    MODEL_MOBILE_DEVICE,
    MODEL_RES_PARTNER,
)
from odoo.addons.sol_laboratory.models.mixins.audit_mixin import mask_text


@tagged("post_install", "-at_install")
class TestAuditMasking(AuditCase):
    def test_a_secret_field_records_that_it_changed_without_its_values(self):
        field = self.env[MODEL_CHEMICAL]._fields["cas_number"]
        field.audit_mask = MASK_SECRET
        self.addCleanup(delattr, field, "audit_mask")
        chemical = self.env[MODEL_CHEMICAL].create({"code": "HC-101", "name": "Acetonitrile", "cas_number": "75-05-8"})

        chemical.cas_number = "75-05-9"

        self.assertEqual(self.changes(self.entries(chemical, "create"))["cas_number"], (False, "***"))
        self.assertEqual(self.changes(self.entries(chemical, "edit")), {"cas_number": ("***", "***")})

    def test_a_personal_field_keeps_only_enough_to_tell_values_apart(self):
        field = self.env[MODEL_CHEMICAL]._fields["cas_number"]
        field.audit_mask = MASK_PERSONAL
        self.addCleanup(delattr, field, "audit_mask")
        chemical = self.env[MODEL_CHEMICAL].create({"code": "HC-102", "name": "Acetonitrile", "cas_number": "75-05-8"})

        chemical.cas_number = "75-05-9"

        self.assertEqual(self.changes(self.entries(chemical, "edit")), {"cas_number": ("***5-8", "***5-9")})

    def test_a_contact_keeps_its_email_phone_and_address_only_in_part(self):
        contact = self.env[MODEL_RES_PARTNER].create(
            {"name": "Nguyen Van An", "email": "an.nguyen@example.com", "phone": "0901234567", "street": "12 Le Loi"}
        )

        changes = self.changes(self.entries(contact, "create"))

        self.assertEqual(changes["email"], (False, "a***@example.com"))
        self.assertEqual(changes["phone"], (False, "***567"))
        self.assertEqual(changes["street"], (False, "***Loi"))
        self.assertEqual(changes["name"], (False, "Nguyen Van An"))

    def test_values_recorded_before_their_field_was_masked_are_masked_on_upgrade(self):
        contact = self.env[MODEL_RES_PARTNER].create({"name": "Tran Thi Binh"})
        entry = (
            self.env[MODEL_AUDIT_ENTRY]
            .sudo()
            .create(
                {
                    "source": "screen",
                    "action": "edit",
                    "document_model": MODEL_RES_PARTNER,
                    "document_id": contact.id,
                    "change_ids": [Command.create({"field_name": "email", "new_value": "binh.tran@example.com"})],
                }
            )
        )

        self.env[MODEL_AUDIT_CHANGE]._mask_recorded_values()

        entry.change_ids.invalidate_recordset()
        self.assertEqual(entry.change_ids.new_value, "b***@example.com")

    def test_a_masked_value_is_masked_once(self):
        self.assertEqual(mask_text(MASK_PERSONAL, "char", "***567"), "***567")
        self.assertEqual(mask_text(MASK_PERSONAL, "char", "a***@example.com"), "a***@example.com")
        self.assertEqual(mask_text(MASK_PERSONAL, "char", "0123"), "***")
        self.assertEqual(mask_text(MASK_PERSONAL, "date", "1990-01-31"), "***")
        self.assertEqual(mask_text(MASK_SECRET, "char", "a-long-secret"), "***")

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
