from odoo.fields import Command
from odoo.tests import Form, tagged

from .common import PricingCase
from odoo.addons.commerce.constants.models import MODEL_PARAMETER_PRICE

ONCHANGE_LOGGER = "odoo.tests.form.onchange"


@tagged("post_install", "-at_install")
class TestServicePackage(PricingCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cadmium = cls.create_parameter("Cadmium (Cd)", cls.group)
        cls.env[MODEL_PARAMETER_PRICE].create(
            {"parameter_id": cls.cadmium.id, "list_price": 100000, "tax_id": cls.vat.id}
        )

    def test_same_parameter_raises_the_quantity(self):
        package = self.create_package(400000, (self.parameter, 1), (self.parameter, 2))

        package.line_ids = [Command.create({"parameter_id": self.parameter.id})]

        self.assertEqual(package.line_ids.mapped("quantity"), [4])

    def test_same_parameter_added_in_the_form_raises_the_quantity(self):
        package = self.create_package(400000, (self.parameter, 1))

        with Form(package) as form, form.line_ids.new() as line:
            line.parameter_id = self.parameter

        self.assertEqual(package.line_ids.mapped("quantity"), [2])

    def test_package_below_its_parts_is_not_overpriced(self):
        package = self.create_package(350000, (self.parameter, 2), (self.cadmium, 1))

        self.assertEqual(package.parts_price, 400000)
        self.assertFalse(package.is_overpriced)

    def test_lowering_a_parameter_price_warns_on_the_package_and_the_price(self):
        package = self.create_package(350000, (self.parameter, 2), (self.cadmium, 1))

        with self.assertLogs(ONCHANGE_LOGGER, "WARNING") as warnings, Form(self.lead_price) as form:
            form.list_price = 100000

        self.assertIn(package.name, warnings.output[0])
        self.assertTrue(package.is_overpriced)

    def test_lowering_a_price_within_the_package_margin_or_for_an_archived_package_does_not_warn(self):
        self.create_package(350000, (self.parameter, 2), (self.cadmium, 1))
        self.create_package(140000, (self.parameter, 1)).action_archive()

        with self.assertNoLogs(ONCHANGE_LOGGER, "WARNING"), Form(self.lead_price) as form:
            form.list_price = 130000

    def test_new_prices_are_rounded_to_the_dong(self):
        package = self.create_package(350000.4, (self.parameter, 1))

        package.invalidate_recordset()

        self.assertEqual(package.list_price, 350000)
