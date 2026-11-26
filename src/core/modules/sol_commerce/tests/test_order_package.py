from odoo.exceptions import UserError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_PRODUCT_TEMPLATE


@tagged("post_install", "-at_install")
class TestOrderPackage(OrderCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.arsenic = cls.create_parameter("Arsenic (As)", cls.group)
        cls.create_price(cls.arsenic, 60000)

    def cart(self):
        return self.make_order([])

    def package_line(self, order):
        return order._catalog_lines().filtered(lambda line: line.product_id.product_tmpl_id == self.package_product)

    def test_a_package_line_costs_the_sum_of_its_parameters(self):
        order = self.make_order([(self.package_product, 2)])

        self.assertEqual(self.package_line(order).price_unit, 150000 + 80000)
        self.assertEqual(order.catalog_total, 2 * 230000)

    def test_unticking_a_parameter_drops_its_price(self):
        order = self.cart()

        order.add_catalog_product(self.package_product, 1, self.parameter)

        line = self.package_line(order)
        self.assertEqual(line._package_parameter_ids(), self.parameter)
        self.assertEqual(line.price_unit, 150000)

    def test_adding_a_parameter_adds_its_price(self):
        order = self.cart()

        order.add_catalog_product(self.package_product, 2, self.parameter | self.other | self.arsenic)

        line = self.package_line(order)
        self.assertEqual(line._package_parameter_ids(), self.parameter | self.other | self.arsenic)
        self.assertEqual(line.price_unit, 150000 + 80000 + 60000)
        self.assertEqual(
            line.linked_line_ids.filtered(
                lambda part: part.product_id.product_tmpl_id.parameter_id == self.arsenic
            ).product_uom_qty,
            2,
        )

    def test_a_package_keeps_at_least_one_parameter(self):
        order = self.cart()

        with self.assertRaisesRegex(UserError, "at least one parameter"):
            order.add_catalog_product(self.package_product, 1, self.parameter.browse())

    def test_the_same_choice_raises_the_quantity_and_another_choice_adds_a_line(self):
        order = self.cart()

        order.add_catalog_product(self.package_product, 1)
        order.add_catalog_product(self.package_product, 1, self.parameter | self.other)
        order.add_catalog_product(self.package_product, 1, self.other)

        lines = self.package_line(order)
        self.assertEqual(sorted(lines.mapped("product_uom_qty")), [1, 2])
        self.assertEqual(sorted(lines.mapped("price_unit")), [80000, 230000])

    def test_the_package_page_offers_the_parameters_it_does_not_hold(self):
        extras = self.package_product._package_extras()

        self.assertIn(self.arsenic, extras.parameter_id)
        self.assertNotIn(self.parameter, extras.parameter_id)
        self.assertNotIn(self.other, extras.parameter_id)
        self.assertFalse(extras - self.env[MODEL_PRODUCT_TEMPLATE].search([("sale_ok", "=", True)]))
