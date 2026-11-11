from odoo.tests import tagged

from .laboratory_files_case import LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY, MODEL_LABORATORY_DEVICE


@tagged("post_install", "-at_install")
class TestLaboratoryDeviceAudit(LaboratoryFilesCase):
    def test_signing_a_computer_in_and_out_and_revoking_it_are_recorded(self):
        device, key = self.sign_in(self.tester, "installation")
        self.device_of(key)._sign_out()
        self.sign_in(self.tester, "installation")
        device.with_user(self.administrator).action_revoke()

        entries = self.env[MODEL_AUDIT_ENTRY].search(
            [("document_model", "=", MODEL_LABORATORY_DEVICE), ("document_id", "=", device.id)], order="id"
        )
        changed = [set(entry.change_ids.mapped("field_name")) for entry in entries]

        self.assertEqual(entries.mapped("action"), ["create", "edit", "edit", "edit"])
        self.assertEqual(entries.user_id.mapped("login"), [self.tester.login, self.administrator.login])
        self.assertIn("api_key_id", changed[0])
        self.assertEqual(changed[1], {"api_key_id"})
        self.assertIn("api_key_id", changed[2])
        self.assertEqual(changed[3], {"api_key_id", "revoked_at"})
