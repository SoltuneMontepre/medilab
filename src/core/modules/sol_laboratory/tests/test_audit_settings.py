from odoo.tests import tagged

from .audit_case import AuditCase

KEY = "medilab.quotation_payment_days"


@tagged("post_install", "-at_install")
class TestAuditSettings(AuditCase):
    def test_a_changed_setting_records_its_key_and_values(self):
        parameters = self.env["ir.config_parameter"].with_user(self.editor)
        parameters.set_str(KEY, "7")
        parameter = parameters.sudo().search([("key", "=", KEY)])

        parameters.set_str(KEY, "10")
        parameter.with_user(self.editor).unlink()

        created, edited, deleted = (self.entries(parameter, action) for action in ("create", "edit", "delete"))
        self.assertEqual((created.note, edited.note, deleted.note), (KEY, KEY, KEY))
        self.assertEqual(self.changes(created)["value"], (False, "7"))
        self.assertEqual(self.changes(edited), {"value": ("7", "10")})
        self.assertEqual(edited.user_id, self.editor)
