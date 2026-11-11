from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce import keep_order_numbers
from odoo.addons.sol_commerce.constants.models import MODEL_BASE_MODULE_UNINSTALL
from odoo.addons.sol_commerce.constants.xml_ids import MODULE
from odoo.addons.sol_laboratory.constants.xml_ids import MODULE as LABORATORY_MODULE


@tagged("post_install", "-at_install")
class TestUninstallWarning(OrderCase):
    """Uninstalling E-commerce warns first and leaves each test request its order's number (SH-01)."""

    def uninstall_wizard(self, name):
        module = self.env["ir.module.module"].search([("name", "=", name)])
        return self.env[MODEL_BASE_MODULE_UNINSTALL].create({"module_ids": module.ids})

    def test_uninstalling_ecommerce_warns_first(self):
        self.assertTrue(self.uninstall_wizard(MODULE).commerce_warning)

    def test_uninstalling_laboratory_does_not_warn_about_order_numbers(self):
        wizard = self.uninstall_wizard(LABORATORY_MODULE)

        self.assertIn(MODULE, wizard._get_modules().mapped("name"))
        self.assertFalse(wizard.commerce_warning)

    def test_the_uninstall_hook_keeps_the_order_number_on_the_test_request(self):
        order = self.make_confirmed_order()
        request = order.test_request_id
        self.assertFalse(request.order_number)

        keep_order_numbers(self.env)

        self.assertEqual(request.order_number, order.name)
