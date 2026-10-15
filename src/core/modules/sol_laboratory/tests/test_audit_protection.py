from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .audit_case import AuditCase
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY


@tagged("post_install", "-at_install")
class TestAuditProtection(AuditCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.administrator = new_test_user(
            cls.env, login="administrator", groups="base.group_user,sol_laboratory.group_role_administrator"
        )
        cls.entry = cls.entries(cls.limit, "create")

    def test_an_administrator_cannot_edit_or_remove_an_entry(self):
        entry = self.entry.with_user(self.administrator)
        refused = (
            lambda: entry.write({"note": "Nothing happened"}),
            entry.unlink,
            lambda: entry.change_ids.write({"new_value": "0.5"}),
            entry.change_ids.unlink,
        )
        for action in refused:
            with self.subTest(action=action), self.assertRaises((AccessError, UserError)):
                action()
        self.assertTrue(self.entry.exists())

    def test_full_rights_cannot_edit_or_remove_an_entry_either(self):
        entry = self.entry.sudo()
        refused = (lambda: entry.write({"note": "Nothing happened"}), entry.unlink, entry.change_ids.unlink)
        for action in refused:
            with self.subTest(action=action), self.assertRaises(UserError):
                action()

    def test_nobody_writes_an_entry_by_hand(self):
        with self.assertRaises(AccessError):
            self.env[MODEL_AUDIT_ENTRY].with_user(self.administrator).create({"source": "screen", "action": "sign"})
