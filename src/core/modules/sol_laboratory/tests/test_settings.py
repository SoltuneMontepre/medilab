from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools.safe_eval import safe_eval

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS
from odoo.addons.sol_laboratory.constants.settings import DEFAULT_SAFETY_MARGIN_DAYS, SAFETY_MARGIN_PARAMETER
from odoo.addons.sol_laboratory.tests.assertions import assert_instance

SETTINGS_MENU = "sol_laboratory.menu_settings"
CONFIGURATION_MENU = "sol_laboratory.menu_laboratory_configuration"
LABORATORY_APP = "sol_laboratory.menu_laboratory_root"
ODOO_SETTINGS_APP = "base.menu_administration"


@tagged("post_install", "-at_install")
class TestSettings(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.clerk = new_test_user(cls.env, login="clerk")
        cls.administrator = new_test_user(
            cls.env, login="settings.administrator", groups="base.group_user,sol_laboratory.group_role_administrator"
        )

    def settings(self, user):
        return self.env[MODEL_RES_CONFIG_SETTINGS].with_user(user)

    def test_missing_parameter_falls_back_to_the_default(self):
        self.env["ir.config_parameter"].search([("key", "=", SAFETY_MARGIN_PARAMETER)]).unlink()

        self.assertEqual(self.settings(self.clerk)._get_parameter("safety_margin_days"), DEFAULT_SAFETY_MARGIN_DAYS)

    def test_stored_parameter_is_read_back(self):
        self.settings(self.administrator).create({"safety_margin_days": 5}).set_values()

        self.assertEqual(self.settings(self.clerk)._get_parameter("safety_margin_days"), 5)

    def test_only_administrators_change_settings(self):
        parameters = self.env["ir.config_parameter"].with_user(self.clerk)
        refused = (
            lambda: self.settings(self.clerk).create({}),
            lambda: parameters.set_str(SAFETY_MARGIN_PARAMETER, "4"),
            lambda: parameters.get_str(SAFETY_MARGIN_PARAMETER),
        )
        for action in refused:
            with self.subTest(action=action), self.assertRaises(AccessError):
                action()
        self.assertTrue(self.settings(self.administrator).create({}))

    def test_settings_menu_is_for_administrators(self):
        menus = set((self.env.ref(CONFIGURATION_MENU) | self.env.ref(SETTINGS_MENU)).ids)
        visible = self.env["ir.ui.menu"].with_user(self.administrator)._visible_menu_ids()
        hidden = self.env["ir.ui.menu"].with_user(self.clerk)._visible_menu_ids()

        self.assertTrue(menus <= visible)
        self.assertTrue(menus.isdisjoint(hidden))

    def test_settings_menu_is_in_the_laboratory_app(self):
        menu = self.env.ref(SETTINGS_MENU)

        self.assertEqual(menu.parent_id, self.env.ref(CONFIGURATION_MENU))
        self.assertEqual(menu.parent_id.parent_id, self.env.ref(LABORATORY_APP))

    def test_odoos_settings_app_is_the_only_settings_app(self):
        apps = self.env["ir.ui.menu"].search([("parent_id", "=", False), ("name", "=", "Settings")])

        self.assertEqual(apps, self.env.ref(ODOO_SETTINGS_APP))

    def test_settings_screen_shows_the_laboratory_app(self):
        arch = self.settings(self.administrator).get_views([(False, "form")])["views"]["form"]["arch"]
        root = etree.fromstring(arch)

        self.assertTrue(root.xpath("//app[@name='sol_laboratory']/block[@name='codes_setting_container']"))
        self.assertTrue(root.xpath("//app[@name='sol_laboratory']//setting[@id='medilab_code_formats']"))
        self.assertTrue(root.xpath("//app[@name='sol_laboratory']//field[@name='safety_margin_days']"))

    def test_code_formats_lists_the_medilab_sequences(self):
        action = self.env.ref("sol_laboratory.action_medilab_code_formats")
        sequences = self.env["ir.sequence"].search(safe_eval(action.domain))

        self.assertTrue(sequences)
        self.assertTrue(all(assert_instance(code, str).startswith("medilab.") for code in sequences.mapped("code")))
