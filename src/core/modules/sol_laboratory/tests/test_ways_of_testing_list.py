from lxml import etree

from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import new_test_user, tagged

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_PARAMETER
from odoo.addons.sol_laboratory.services.record_id import persisted_id

PARAMETER_EDITOR_GROUPS = (
    "base.group_user,"
    "sol_laboratory.group_permission_test_parameter_edit_all,"
    "sol_laboratory.group_permission_parameter_method_archive_all"
)


@tagged("post_install", "-at_install")
class TestWaysOfTestingList(MasterDataCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Edits parameters and archives their ways of testing, but holds no delete permission.
        cls.editor = new_test_user(cls.env, login="parameter.editor", groups=PARAMETER_EDITOR_GROUPS)

    def test_ways_of_testing_list_offers_archiving_but_not_deleting(self):
        arch = self.env[MODEL_TEST_PARAMETER].get_views([(False, "form")])["views"]["form"]["arch"]
        rows = etree.fromstring(arch).findall(".//field[@name='method_ids']/list")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("delete"), "0")
        self.assertTrue(rows[0].xpath("field[@name='active']"))

    def test_active_toggle_archives_and_restores_a_way_of_testing_from_the_form(self):
        parameter = self.parameter.with_user(self.editor)

        parameter.write({"method_ids": [Command.update(persisted_id(self.pair), {"active": False})]})
        self.assertFalse(self.pair.active)

        parameter.write({"method_ids": [Command.update(persisted_id(self.pair), {"active": True})]})
        self.assertTrue(self.pair.active)

    def test_commands_of_the_parameter_never_delete_a_way_of_testing(self):
        administrator = self.env.ref("base.user_admin")
        commands = {
            "delete": Command.delete(persisted_id(self.pair)),
            "unlink": Command.unlink(persisted_id(self.pair)),
            "clear": Command.clear(),
        }
        for user in (self.editor, administrator):
            for name, command in commands.items():
                with self.subTest(user=user.login, command=name), self.assertRaises((AccessError, UserError)):
                    self.parameter.with_user(user).write({"method_ids": [command]})
        for name, command in commands.items():
            with self.subTest(user="superuser", command=name), self.assertRaises(UserError):
                self.parameter.sudo().write({"method_ids": [command]})

        self.assertTrue(self.pair.exists())
        self.assertEqual(self.pair.parameter_id, self.parameter)
