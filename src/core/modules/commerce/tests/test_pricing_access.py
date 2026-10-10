from lxml import etree

from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import new_test_user, tagged

from .common import PricingCase
from odoo.addons.commerce.constants.models import (
    MODEL_PARAMETER_PRICE,
    MODEL_SERVICE_PACKAGE,
    MODEL_SERVICE_PACKAGE_LINE,
    MODEL_SUBCONTRACT_COST,
    MODEL_TAX,
    MODEL_TAX_RATE,
)

PRICING_MODELS = [
    MODEL_PARAMETER_PRICE,
    MODEL_SERVICE_PACKAGE,
    MODEL_SERVICE_PACKAGE_LINE,
    MODEL_SUBCONTRACT_COST,
    MODEL_TAX,
    MODEL_TAX_RATE,
]


@tagged("post_install", "-at_install")
class TestPricingAccess(PricingCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sales = new_test_user(cls.env, login="sales", groups="base.group_user")
        cls.administrator = cls.env.ref("base.user_admin")
        cls.package = cls.create_package(120000, (cls.parameter, 1))

    def test_non_administrator_reads_but_cannot_change(self):
        tax = self.vat.with_user(self.sales)
        price = self.lead_price.with_user(self.sales)
        package = self.package.with_user(self.sales)

        self.assertEqual((price.list_price, price.tax_id.code), (150000, "VAT10"))
        self.assertEqual(package.line_ids.parameter_id, self.parameter)
        self.assertEqual(tax.rate_ids.mapped("rate"), [8, 10])
        for action in (
            lambda: tax.create({"code": "VAT5", "name": "VAT 5%"}),
            lambda: price.write({"list_price": 1}),
            lambda: package.write({"line_ids": [Command.create({"parameter_id": self.parameter.id})]}),
            lambda: tax.rate_ids[0].write({"rate": 5}),
            tax.action_archive,
            package.unlink,
        ):
            with self.subTest(action=action), self.assertRaises(AccessError):
                action()

    def test_non_administrator_sees_no_actions(self):
        for model in PRICING_MODELS:
            records = self.env[model].with_user(self.sales)
            for view_type, view in records.get_views([(False, "list"), (False, "form")])["views"].items():
                root = etree.fromstring(view["arch"])
                with self.subTest(model=model, view=view_type):
                    self.assertEqual(
                        [root.get("create"), root.get("edit"), root.get("delete")], ["False", "False", "False"]
                    )

    def test_administrator_changes_prices_taxes_and_packages(self):
        self.lead_price.with_user(self.administrator).list_price = 160000
        self.package.with_user(self.administrator).action_archive()
        tax = self.env[MODEL_TAX].with_user(self.administrator).create({"code": "VAT5", "name": "VAT 5%"})
        tax.unlink()

        self.assertEqual(self.lead_price.list_price, 160000)
        self.assertFalse(self.package.active)
        self.assertFalse(tax.exists())
