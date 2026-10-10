from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from .common import PricingCase
from odoo.addons.commerce.constants.models import MODEL_TAX


@tagged("post_install", "-at_install")
class TestTaxArchiving(PricingCase):
    def test_tax_of_active_price_or_package_cannot_be_archived(self):
        package = self.create_package(300000, (self.parameter, 2))

        with self.assertRaises(UserError) as refusal:
            self.vat.action_archive()

        self.assertIn(self.parameter.name, str(refusal.exception))
        self.assertIn(package.name, str(refusal.exception))

    def test_tax_of_archived_price_and_package_can_be_archived_but_not_deleted(self):
        package = self.create_package(300000, (self.parameter, 2))
        self.lead_price.action_archive()
        package.action_archive()

        self.vat.action_archive()

        self.assertFalse(self.vat.active)
        with self.assertRaises(UserError):
            self.vat.unlink()

    def test_unused_tax_is_deleted_with_its_rates(self):
        tax = self.env[MODEL_TAX].create(
            {
                "code": "TEST-KCT",
                "name": "Not subject to VAT",
                "rate_ids": [Command.create({"rate": 0, "valid_from": "2020-01-01"})],
            }
        )
        rates = tax.rate_ids

        tax.unlink()

        self.assertFalse(rates.exists())

    def test_parameter_of_active_package_cannot_be_archived(self):
        package = self.create_package(300000, (self.parameter, 2))

        with self.assertRaises(UserError):
            self.parameter.action_archive()

        package.action_archive()
        self.parameter.action_archive()
        self.assertFalse(self.parameter.active)
