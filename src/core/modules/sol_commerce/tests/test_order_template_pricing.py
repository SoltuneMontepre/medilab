from odoo.fields import Command
from odoo.tests import tagged

from .template_case import TemplateCase


@tagged("post_install", "-at_install")
class TestOrderTemplatePricing(TemplateCase):
    def ordinary(self, product, quantity, fiscal_position):
        return (
            self.env["sale.order"]
            .with_user(self.sales)
            .with_context(medilab_sales_order=True)
            .create(
                {
                    "customer_id": self.customer.id,
                    "partner_id": self.contact.id,
                    "fiscal_position_id": fiscal_position.id,
                    "order_line": [
                        Command.create({"product_id": product.product_variant_ids.id, "product_uom_qty": quantity})
                    ],
                }
            )
        )

    def test_current_prices_and_zero_discounts_replace_source_values(self):
        source = self.template_source()
        source._catalog_lines().write({"price_unit": 1, "discount": 25})
        template = self.save_template(source)
        self.lead_price.list_price = 160000
        self.package.list_price = 120000
        order = self.reuse(template)
        self.assertEqual(order._catalog_lines().mapped("price_unit"), [160000, 120000])
        self.assertEqual(order._catalog_lines().mapped("discount"), [0, 0])
        self.assertEqual(order.amount_untaxed, 510000)
        self.assertEqual(source._catalog_lines().mapped("price_unit"), [1, 1])

    def test_native_taxes_and_fiscal_positions_match_ordinary_sales(self):
        for rate in (0, 8, 10):
            tax = self.env["account.tax"].create(
                {"name": f"Current VAT {rate}", "amount": rate, "type_tax_use": "sale"}
            )
            for product, quantity, untaxed in ((self.lead_product, 1.5, 225000), (self.package_product, 2.25, 225000)):
                with self.subTest(rate=rate, product=product.name):
                    product.taxes_id = tax
                    fpos = self.env.company.domestic_fiscal_position_id
                    self.contact.property_account_position_id = fpos
                    source = self.ordinary(product, quantity, fpos)
                    template = self.save_template(source)
                    order = self.reuse(template)
                    ordinary = self.ordinary(product, quantity, fpos)
                    self.assertEqual(order.fiscal_position_id, ordinary.fiscal_position_id)
                    self.assertEqual(order._catalog_lines().tax_ids, ordinary._catalog_lines().tax_ids)
                    self.assertEqual(order.amount_untaxed, untaxed)
                    self.assertEqual(order.amount_tax, untaxed * rate / 100)
                    self.assertEqual(order.amount_total, ordinary.amount_total)
                    self.assertEqual(order.amount_tax, ordinary.amount_tax)

    def test_customer_fiscal_position_mapping_is_recomputed(self):
        original = self.env["account.tax"].create({"name": "Original VAT 10", "amount": 10, "type_tax_use": "sale"})
        position = self.env["account.fiscal.position"].create({"name": "Mapped VAT"})
        reduced = self.env["account.tax"].create(
            {
                "name": "Mapped VAT 8",
                "amount": 8,
                "type_tax_use": "sale",
                "original_tax_ids": [Command.set(original.ids)],
                "fiscal_position_ids": [Command.set(position.ids)],
            }
        )
        self.lead_product.taxes_id = original
        self.contact.property_account_position_id = position
        template = self.save_template(self.template_source([(self.lead_product, 2)]))
        order = self.reuse(template)
        ordinary = self.ordinary(self.lead_product, 2, position)
        self.assertEqual(order.fiscal_position_id, position)
        self.assertEqual(order._catalog_lines().tax_ids, reduced)
        self.assertEqual(order.amount_tax, 24000)
        self.assertEqual(order.amount_total, ordinary.amount_total)

    def test_known_catalog_tax_gap_is_also_present_in_ordinary_sales(self):
        # Characterizes the separate defect: medilab.tax is not mapped to native product taxes.
        self.assertEqual(self.vat._rate_on(self.env["sale.order"].default_get(["date_order"])["date_order"].date()), 10)
        position = self.env.company.domestic_fiscal_position_id
        for product, untaxed in ((self.lead_product, 300000), (self.package_product, 200000)):
            with self.subTest(product=product.name):
                self.assertFalse(product.taxes_id)
                ordinary = self.ordinary(product, 2, position)
                template = self.save_template(ordinary)
                created = self.reuse(template)
                self.assertEqual(ordinary.amount_untaxed, untaxed)
                self.assertEqual(ordinary.amount_tax, 0)
                self.assertEqual(created.amount_tax, ordinary.amount_tax)
