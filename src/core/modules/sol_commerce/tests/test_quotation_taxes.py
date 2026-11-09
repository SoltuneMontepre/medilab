from datetime import date, datetime

from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER_DISCOUNT, MODEL_TAX
from odoo.addons.sol_commerce.constants.xml_ids import DISCOUNT_PRODUCT
from odoo.addons.sol_laboratory.services.record_id import persisted_ids


@tagged("post_install", "-at_install")
class TestQuotationTaxes(OrderCase):
    """A quotation line takes the tax of its parameter or package at the rate in force on the quotation date."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vat10 = cls.chart_tax("tax_sale_vat10")
        cls.vat8 = cls.chart_tax("tax_sale_vat8")
        cls.vat0 = cls.chart_tax("tax_sale_vat0")
        cls.exemption = cls.chart_tax("tax_sale_vat_exemption")

    @classmethod
    def chart_tax(cls, name):
        """The company's sales tax of the Vietnamese chart of accounts."""
        tax = cls.env["account.chart.template"].ref(name)
        assert tax is not None
        return cls.env["account.tax"].browse(persisted_ids(tax))

    def sales_order(self, lines, **vals):
        """An order sales creates on the Orders screen."""
        return (
            self.env["sale.order"]
            .with_user(self.sales)
            .with_context(medilab_sales_order=True)
            .create(
                {
                    "customer_id": self.customer.id,
                    "partner_id": self.contact.id,
                    "order_line": [
                        Command.create({"product_id": product.product_variant_ids.id, "product_uom_qty": quantity})
                        for product, quantity in lines
                    ],
                    **vals,
                }
            )
        )

    def not_subject_tax(self):
        return self.env[MODEL_TAX].create(
            {
                "code": "KCT",
                "name": "Not subject to VAT",
                "rate_ids": [Command.create({"rate": 0, "valid_from": date(2020, 1, 1)})],
            }
        )

    def test_order_screen_lines_carry_the_vat_of_their_parameter_and_package(self):
        order = self.sales_order([(self.lead_product, 2), (self.package_product, 1)])

        self.assertEqual(order._catalog_lines().tax_ids, self.vat10)
        self.assertEqual(order.amount_untaxed, 400000)
        self.assertEqual(order.amount_tax, 40000)
        self.assertEqual(order.amount_total, 440000)

    def test_portal_cart_lines_carry_the_vat(self):
        order = self.make_order([(self.lead_product, 3)])

        self.assertEqual(order._catalog_lines().tax_ids, self.vat10)
        self.assertEqual(order.catalog_total, 450000)
        self.assertEqual(order.amount_tax, 45000)

    def test_the_rate_in_force_on_the_quotation_date_applies(self):
        order = self.sales_order([(self.lead_product, 1)], date_order=datetime(2025, 3, 15, 9))
        line = order._catalog_lines()
        self.assertEqual(line.tax_ids, self.vat8)
        self.assertEqual(order.amount_tax, 12000)

        order.date_order = datetime(2025, 7, 1, 9)

        self.assertEqual(line.tax_ids, self.vat10)
        self.assertEqual(order.amount_tax, 15000)

    def test_a_new_quotation_date_leaves_the_whole_quotation_discount_taxes(self):
        order = self.sales_order([(self.lead_product, 2)])
        self.env[MODEL_SALE_ORDER_DISCOUNT].with_context(active_id=order.id).create(
            {"discount_type": "so_discount", "discount_percentage": 0.1}
        ).action_apply_discount()
        discount = order.order_line.filtered(lambda line: line.product_id == self.env.ref(DISCOUNT_PRODUCT))
        self.assertEqual(discount.tax_ids, self.vat10)

        order.date_order = datetime(2025, 3, 15, 9)

        self.assertEqual(order._catalog_lines().tax_ids, self.vat8)
        self.assertEqual(discount.tax_ids, self.vat10)

    def test_a_date_without_a_rate_is_refused(self):
        with self.assertRaisesRegex(UserError, "has no rate on"):
            self.sales_order([(self.lead_product, 1)], date_order=datetime(2024, 12, 31, 9))

    def test_the_accounting_tax_chosen_on_the_rate_applies(self):
        rate = self.vat.rate_ids.filtered(lambda period: period.rate == 10)
        other = self.env["account.tax"].create({"name": "Other VAT 10", "amount": 10, "type_tax_use": "sale"})

        rate.account_tax_id = other

        self.assertEqual(self.sales_order([(self.lead_product, 1)])._catalog_lines().tax_ids, other)

    def test_the_tax_not_subject_to_vat_takes_the_chart_exemption(self):
        self.lead_price.tax_id = self.not_subject_tax()

        order = self.sales_order([(self.lead_product, 1)])

        self.assertEqual(order._catalog_lines().tax_ids, self.exemption)
        self.assertEqual(order.amount_total, 150000)

    def test_an_archived_chart_exemption_leaves_the_chart_0_percent_vat(self):
        self.lead_price.tax_id = self.not_subject_tax()
        self.exemption.active = False

        self.assertEqual(self.sales_order([(self.lead_product, 1)])._catalog_lines().tax_ids, self.vat0)

    def test_another_tax_of_0_percent_takes_the_chart_0_percent_vat(self):
        self.lead_price.tax_id = self.env[MODEL_TAX].create(
            {
                "code": "VAT0",
                "name": "VAT 0%",
                "rate_ids": [Command.create({"rate": 0, "valid_from": date(2020, 1, 1)})],
            }
        )

        self.assertEqual(self.sales_order([(self.lead_product, 1)])._catalog_lines().tax_ids, self.vat0)

    def test_a_cart_line_without_a_rate_gets_its_tax_when_the_quotation_is_sent(self):
        current = self.vat.rate_ids.filtered(lambda period: period.rate == 10)
        current.valid_until = date(2025, 12, 31)
        order = (
            self.env["sale.order"]
            .with_user(self.portal)
            .sudo()
            .create(
                {
                    "partner_id": self.contact.id,
                    "customer_id": self.customer.id,
                    "source": "portal",
                    "order_status": "claimed",
                    "user_id": self.sales.id,
                    "advance_method": "cash",
                    "advance_mode": "full",
                    "order_line": [Command.create({"product_id": self.lead_product.product_variant_ids.id})],
                }
            )
        )
        line = order._catalog_lines()
        self.assertFalse(line.tax_ids)
        line.sample_id = self.make_sample(order)

        with self.assertRaisesRegex(UserError, "has no rate on"):
            order.with_user(self.sales).action_send_quotation()
        self.assertFalse(order.quotation_ids)

        self.env["medilab.tax.rate"].create({"tax_id": self.vat.id, "rate": 10, "valid_from": date(2026, 1, 1)})
        order.with_user(self.sales).action_send_quotation()

        self.assertEqual(line.tax_ids, self.vat10)
        self.assertEqual(order._latest_quotation().amount_total, 165000)

    def test_an_accounting_tax_of_another_rate_is_refused(self):
        rate = self.vat.rate_ids.filtered(lambda period: period.rate == 10)

        with self.assertRaisesRegex(ValidationError, "must be a sales tax of 10%"):
            rate.account_tax_id = self.vat8

    def test_a_rate_without_an_accounting_tax_is_refused(self):
        self.vat.rate_ids.filtered(lambda period: period.rate == 10).rate = 7

        with self.assertRaisesRegex(UserError, "Accounting has no sales tax"):
            self.sales_order([(self.lead_product, 1)])

    def test_sales_can_change_the_tax_of_a_line(self):
        order = self.sales_order([(self.lead_product, 1)])
        line = order._catalog_lines()

        line.with_user(self.sales).tax_ids = self.vat0

        self.assertEqual(line.tax_ids, self.vat0)
        self.assertEqual(order.amount_total, 150000)

    def test_the_quotation_and_its_advance_invoice_carry_the_vat(self):
        order = self.sent_order()
        quotation = order._latest_quotation()

        self.assertEqual(quotation.amount_total, 165000)
        invoice = order.sudo().invoice_ids
        self.assertEqual(invoice.amount_tax, 15000)
        self.assertEqual(invoice.amount_total, 165000)

    def test_a_sent_quotation_keeps_its_taxes(self):
        order = self.sent_order()
        line = order._catalog_lines()

        self.vat.rate_ids.filtered(lambda period: period.rate == 10).account_tax_id = self.env["account.tax"].create(
            {"name": "Other VAT 10", "amount": 10, "type_tax_use": "sale"}
        )
        order.sudo().date_order = datetime(2025, 3, 15, 9)

        self.assertEqual(line.tax_ids, self.vat10)

    def test_untaxed_lines_of_unsent_orders_get_their_tax(self):
        draft = self.make_order([(self.lead_product, 1)])
        claimed = self.make_order([(self.lead_product, 1)], status="claimed", user_id=self.sales.id)
        sent = self.sent_order()
        confirmed = self.make_order([(self.lead_product, 1)])
        cancelled = self.make_order([(self.lead_product, 1)])
        orders = draft | claimed | sent | confirmed | cancelled
        self.env.cr.execute(
            "DELETE FROM account_tax_sale_order_line_rel WHERE sale_order_line_id = ANY(%s)",
            [orders._catalog_lines().ids],
        )
        self.env.cr.execute(
            "UPDATE sale_order SET order_status = CASE id WHEN %s THEN 'confirmed' ELSE 'cancelled' END WHERE id IN %s",
            [confirmed.id, (confirmed.id, cancelled.id)],
        )
        self.env.invalidate_all()

        self.env["sale.order.line"]._tax_untaxed_drafts()

        self.assertEqual((draft | claimed)._catalog_lines().tax_ids, self.vat10)
        for order in (sent, confirmed, cancelled):
            with self.subTest(order=order.order_status):
                self.assertFalse(order._catalog_lines().tax_ids)

    def test_a_fiscal_position_maps_the_catalog_tax(self):
        position = self.env["account.fiscal.position"].create({"name": "Export"})
        self.env["account.tax"].create(
            {
                "name": "Export VAT 0",
                "amount": 0,
                "type_tax_use": "sale",
                "original_tax_ids": [Command.set(persisted_ids(self.vat10))],
                "fiscal_position_ids": [Command.set(persisted_ids(position))],
            }
        )

        order = self.sales_order([(self.lead_product, 1)], fiscal_position_id=position.id)

        self.assertEqual(order._catalog_lines().tax_ids.name, "Export VAT 0")
        self.assertEqual(order.amount_total, 150000)
