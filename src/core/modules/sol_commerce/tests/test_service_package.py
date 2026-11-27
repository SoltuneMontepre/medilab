from odoo.fields import Command
from odoo.tests import Form, tagged
from odoo.tests.form import O2MProxy

from .common import PricingCase
from odoo.addons.sol_commerce.constants.models import MODEL_PRODUCT_TEMPLATE
from odoo.addons.sol_laboratory.tests.assertions import assert_instance


@tagged("post_install", "-at_install")
class TestServicePackage(PricingCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cadmium = cls.create_parameter("Cadmium (Cd)", cls.group)
        cls.cadmium_price = cls.create_price(cls.cadmium, 100000)

    def product_of(self, package):
        return self.env[MODEL_PRODUCT_TEMPLATE].search([("service_package_id", "=", package.id)])

    def test_same_parameter_raises_the_quantity(self):
        package = self.create_package((self.parameter, 1), (self.parameter, 2))

        package.line_ids = [Command.create({"parameter_id": self.parameter.id})]

        self.assertEqual(package.line_ids.mapped("quantity"), [4])

    def test_same_parameter_added_in_the_form_raises_the_quantity(self):
        package = self.create_package((self.parameter, 1))

        with Form(package) as form, assert_instance(form.line_ids, O2MProxy).new() as line:
            line.parameter_id = self.parameter

        self.assertEqual(package.line_ids.mapped("quantity"), [2])

    def test_package_costs_the_sum_of_its_parameters(self):
        package = self.create_package((self.parameter, 2), (self.cadmium, 1))

        self.assertEqual(package.list_price, 2 * 150000 + 100000)
        self.assertEqual(self.product_of(package).list_price, 400000)

    def test_package_price_follows_a_parameter_price_change(self):
        package = self.create_package((self.parameter, 2), (self.cadmium, 1))

        self.cadmium_price.list_price = 120000

        self.assertEqual(package.list_price, 420000)
        self.assertEqual(self.product_of(package).list_price, 420000)

    def test_package_price_follows_its_parameters_changing(self):
        package = self.create_package((self.parameter, 1))

        package.line_ids = [Command.create({"parameter_id": self.cadmium.id})]

        self.assertEqual(self.product_of(package).list_price, 250000)

    def test_package_with_an_unpriced_parameter_is_not_sold(self):
        unpriced = self.create_parameter("Arsenic (As)", self.group)

        package = self.create_package((self.parameter, 1), (unpriced, 1))

        self.assertFalse(self.product_of(package).sale_ok)
