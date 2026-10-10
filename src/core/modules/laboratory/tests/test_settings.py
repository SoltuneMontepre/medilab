from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools.safe_eval import safe_eval

from odoo.addons.laboratory.constants.models import (
    MODEL_IR_CONFIG_PARAMETER,
    MODEL_IR_SEQUENCE,
    MODEL_RES_CONFIG_SETTINGS,
)

# A settings field that web declares as a system parameter; it exercises the pattern until laboratory declares one.
WEB_APP_NAME = "web_app_name"
WEB_APP_NAME_KEY = "web.web_app_name"
SETTINGS_MENUS = ("laboratory.menu_system_root", "laboratory.menu_settings")


@tagged("post_install", "-at_install")
class TestSettings(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.clerk = new_test_user(cls.env, login="clerk")
        cls.administrator = new_test_user(
            cls.env, login="settings.administrator", groups="base.group_user,laboratory.group_role_administrator"
        )

    def settings(self, user):
        return self.env[MODEL_RES_CONFIG_SETTINGS].with_user(user)

    def visible_menus(self, user):
        visible = self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()
        return {xml_id for xml_id in SETTINGS_MENUS if self.env.ref(xml_id).id in visible}

    def test_missing_parameter_falls_back_to_the_default(self):
        self.env[MODEL_IR_CONFIG_PARAMETER].search([("key", "=", WEB_APP_NAME_KEY)]).unlink()

        self.assertEqual(self.settings(self.clerk)._get_parameter(WEB_APP_NAME), False)

    def test_stored_parameter_is_read_back(self):
        self.settings(self.administrator).create({WEB_APP_NAME: "MediLab QA"}).set_values()

        self.assertEqual(self.settings(self.clerk)._get_parameter(WEB_APP_NAME), "MediLab QA")

    def test_only_administrators_change_settings(self):
        parameters = self.env[MODEL_IR_CONFIG_PARAMETER].with_user(self.clerk)
        refused = (
            lambda: self.settings(self.clerk).create({}),
            lambda: parameters.set_str(WEB_APP_NAME_KEY, "MediLab QA"),
            lambda: parameters.get_str(WEB_APP_NAME_KEY),
        )
        for action in refused:
            with self.subTest(action=action), self.assertRaises(AccessError):
                action()
        self.assertTrue(self.settings(self.administrator).create({}))

    def test_settings_menu_is_for_administrators(self):
        self.assertEqual(self.visible_menus(self.administrator), set(SETTINGS_MENUS))
        self.assertEqual(self.visible_menus(self.clerk), set())

    def test_settings_screen_shows_the_medilab_app_with_the_laboratory_block(self):
        arch = self.settings(self.administrator).get_views([(False, "form")])["views"]["form"]["arch"]
        root = etree.fromstring(arch)

        self.assertTrue(root.xpath("//app[@name='medilab']/block[@name='laboratory']"))
        self.assertTrue(root.xpath("//app[@name='medilab']//setting[@id='medilab_code_formats']"))

    def test_code_formats_lists_the_medilab_sequences(self):
        action = self.env.ref("laboratory.action_medilab_code_formats")

        sequences = self.env[MODEL_IR_SEQUENCE].search(safe_eval(action.domain))

        self.assertTrue(sequences)
        self.assertTrue(all(code.startswith("medilab.") for code in sequences.mapped("code")))
