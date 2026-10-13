from lxml import etree

from odoo.tests import new_test_user, tagged

from .audit_case import AuditCase
from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS
from odoo.addons.sol_laboratory.constants.settings import AUDIT_RETENTION_PARAMETER

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

    def test_the_retention_period_is_a_laboratory_setting_that_keeps_entries_for_ever_by_default(self):
        administrator = new_test_user(
            self.env, login="settings.administrator", groups="base.group_user,sol_laboratory.group_role_administrator"
        )
        settings = self.env[MODEL_RES_CONFIG_SETTINGS].with_user(administrator)
        parameters = self.env["ir.config_parameter"].sudo()
        self.assertFalse(parameters.get_str(AUDIT_RETENTION_PARAMETER))
        self.assertFalse(settings.create({}).audit_retention_days)

        settings.create({"audit_retention_days": 3650}).set_values()

        self.assertEqual(parameters.get_str(AUDIT_RETENTION_PARAMETER), "3650")
        arch = settings.get_views([(False, "form")])["views"]["form"]["arch"]
        self.assertTrue(
            etree.fromstring(arch).xpath("//app[@name='sol_laboratory']//field[@name='audit_retention_days']")
        )
