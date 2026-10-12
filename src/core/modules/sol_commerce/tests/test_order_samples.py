from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .order_case import OrderCase


@tagged("post_install", "-at_install")
class TestOrderSamples(OrderCase):
    def package_line(self, order):
        return order._catalog_lines().filtered(lambda line: line.product_id.product_tmpl_id == self.package_product)

    def test_package_adds_one_free_line_for_each_parameter(self):
        order = self.make_order([(self.package_product, 2)])
        line = self.package_line(order)

        self.assertEqual(line.linked_line_ids.product_id.product_tmpl_id.parameter_id, self.parameter | self.other)
        self.assertEqual(line.linked_line_ids.mapped("price_unit"), [0.0, 0.0])
        self.assertEqual(line.linked_line_ids.mapped("product_uom_qty"), [2.0, 2.0])
        self.assertEqual(order._catalog_lines(), line)
        self.assertEqual(order.catalog_total, self.package.list_price * 2)

    def test_removing_the_package_removes_its_parameters(self):
        order = self.make_order([(self.package_product, 1), (self.lead_product, 1)])
        parts = self.package_line(order).linked_line_ids

        self.package_line(order).unlink()

        self.assertFalse(parts.exists())
        self.assertEqual(len(order.order_line), 1)

    def test_package_quantity_and_sample_reach_its_parameters(self):
        order = self.make_order([(self.package_product, 1)])
        line = self.package_line(order)

        line.product_uom_qty = 3
        line.sample_id = self.make_sample(order)

        self.assertEqual(line.linked_line_ids.mapped("product_uom_qty"), [3.0, 3.0])
        self.assertEqual(line.linked_line_ids.sample_id, line.sample_id)
        self.assertEqual(line.linked_line_ids.mapped("price_unit"), [0.0, 0.0])

    def test_adding_a_package_to_the_cart_adds_its_parameters(self):
        order = self.make_order([])

        order.add_catalog_product(self.package_product, 1)

        self.assertEqual(len(order.order_line), 3)
        self.assertEqual(order.catalog_total, self.package.list_price)

    def test_copying_a_sample_copies_its_lines_with_their_prices(self):
        order = self.make_order([(self.lead_product, 2), (self.package_product, 1)])
        sample = self.make_sample(order)
        order._catalog_lines().sample_id = sample
        order._catalog_lines().filtered(
            lambda line: line.product_id.product_tmpl_id == self.lead_product
        ).price_unit = 1234

        copy = sample.copy_sample()

        self.assertEqual(copy.order_id, order)
        self.assertEqual(copy.customer_sample_name, sample.customer_sample_name)
        self.assertNotEqual(copy, sample)
        self.assertEqual(len(copy.line_ids._catalog_lines()), 2)
        lead = copy.line_ids._catalog_lines().filtered(
            lambda line: line.product_id.product_tmpl_id == self.lead_product
        )
        self.assertEqual((lead.price_unit, lead.product_uom_qty), (1234, 2))
        self.assertEqual(len(copy.line_ids), 4)
        self.assertEqual(len(sample.line_ids), 4)

    def test_a_line_cannot_use_a_sample_of_another_order(self):
        order = self.make_order([(self.lead_product, 1)])
        other = self.make_order([(self.lead_product, 1)])

        with self.assertRaises(ValidationError):
            order._catalog_lines().sample_id = self.make_sample(other)
