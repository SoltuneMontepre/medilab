from datetime import date, timedelta

from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged
from odoo.tests.form import M2MProxy, O2MProxy

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_PRODUCT_TEMPLATE, MODEL_SALE_ORDER
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TYPE
from odoo.addons.sol_laboratory.tests.assertions import assert_instance


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

    def test_an_item_added_to_the_cart_starts_on_a_sample_type_and_shows_its_expected_samples(self):
        order = self.make_order([])

        order.add_catalog_product(self.lead_product, 1)
        line = order._catalog_lines()

        self.assertTrue(line.sample_type_id)
        self.assertTrue(line.parameter_method_id)
        self.assertTrue(order._expected_sampling())

    def test_a_second_item_follows_the_sample_type_the_cart_already_uses(self):
        order = self.make_order([])
        order.add_catalog_product(self.lead_product, 1)
        chosen = order._catalog_lines().sample_type_id

        order.add_catalog_product(self.package_product, 1)

        self.assertEqual(order._catalog_lines().sample_type_id, chosen)
        self.assertEqual(self.package_line(order).linked_line_ids.sample_type_id, chosen)

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

    def test_sending_gives_each_line_a_sample_of_its_sample_type(self):
        order = self.make_order(
            [(self.lead_product, 1)],
            status="claimed",
            user_id=self.sales.id,
            advance_method="cash",
            advance_mode="full",
        )
        line = order._catalog_lines()
        line.sample_type_id = self.sample_type
        self.assertFalse(line.sample_id)

        order.with_user(self.sales).action_send_quotation()

        self.assertEqual(line.sample_id.sample_type_id, line.sample_type_id)
        self.assertEqual(line.sample_id.customer_sample_name, line.sample_type_id.name)
        self.assertFalse(line.sample_id.physical_state)

    def test_a_line_without_a_sample_type_keeps_the_quotation_from_being_sent(self):
        order = self.make_order(
            [(self.lead_product, 1)],
            status="claimed",
            user_id=self.sales.id,
            advance_method="cash",
            advance_mode="full",
        )
        order._catalog_lines().sample_type_id = False

        with self.assertRaisesRegex(UserError, "Choose a sample type"):
            order.with_user(self.sales).action_send_quotation()

    def test_order_line_offers_only_sample_types_supported_by_every_parameter(self):
        surface_water = self.env[MODEL_SAMPLE_TYPE].create({"name": "Surface water", "code": "LM-SURF"})
        cabbage = self.env[MODEL_SAMPLE_TYPE].create({"name": "Cabbage", "code": "LM-CAB"})
        self.offer(self.parameter, surface_water)
        cadmium_product = self.env[MODEL_PRODUCT_TEMPLATE].search([("parameter_id", "=", self.other.id)], limit=1)

        order = self.make_order([(self.lead_product, 1), (self.package_product, 1), (cadmium_product, 1)])
        lead = order._catalog_lines().filtered(lambda line: line.product_id.product_tmpl_id == self.lead_product)
        package = self.package_line(order)
        cadmium = order._catalog_lines() - lead - package

        self.assertEqual(lead.offered_sample_type_ids, self.sample_type | surface_water)
        self.assertEqual(package.offered_sample_type_ids, self.sample_type)
        self.assertEqual(cadmium.offered_sample_type_ids, self.sample_type)
        self.assertNotIn(cabbage, lead.offered_sample_type_ids)

    def test_selecting_a_package_on_the_form_expands_its_parameters_without_duplicating_on_save(self):
        surface_water = self.env[MODEL_SAMPLE_TYPE].create({"name": "Surface water", "code": "LM-FORM-SURF"})
        self.offer(self.parameter, surface_water)
        # The form helper loads every one-to-many's view, support requests included, which Sales cannot read.
        with Form(self.env[MODEL_SALE_ORDER].with_context(medilab_sales_order=True)) as form:
            form.customer_id = self.customer
            form.expected_collection_date = date.today() + timedelta(days=1)
            lines = assert_instance(form.product_line_ids, O2MProxy)
            with lines.new() as line:
                line.product_template_id = self.lead_product
                line.sample_type_id = surface_water
            with lines.edit(0) as line:
                # Switching to the package drops surface_water (unsupported by Cadmium) and fills the sole common type.
                line.product_template_id = self.package_product
            self.assertEqual(len(lines), 3)
            order = form.save()

        self.assertEqual(len(order.order_line), 3)
        package = self.package_line(order)
        self.assertEqual(package.sample_type_id, self.sample_type)
        self.assertEqual(package.linked_line_ids.sample_type_id, self.sample_type)
        self.assertFalse(package.linked_line_ids.tax_ids)
        self.assertEqual(order.quoted_line_ids, package)

    def test_parameter_choices_follow_the_chosen_sample_type(self):
        surface_water = self.env[MODEL_SAMPLE_TYPE].create({"name": "Surface water", "code": "LM-PICK-SURF"})
        self.offer(self.parameter, surface_water)
        cadmium_product = self.env[MODEL_PRODUCT_TEMPLATE].search([("parameter_id", "=", self.other.id)], limit=1)
        products = self.env[MODEL_PRODUCT_TEMPLATE]

        on_surface_water = products.search([("orderable_sample_type_ids", "in", [surface_water.id])])
        on_bottled_water = products.search([("orderable_sample_type_ids", "in", [self.sample_type.id])])

        self.assertIn(self.lead_product, on_surface_water)
        # Cadmium is not offered on surface water, so neither is the package that includes it.
        self.assertNotIn(cadmium_product, on_surface_water)
        self.assertNotIn(self.package_product, on_surface_water)
        self.assertLessEqual(self.lead_product | cadmium_product | self.package_product, on_bottled_water)

    def test_sample_type_can_be_chosen_before_the_parameter(self):
        surface_water = self.env[MODEL_SAMPLE_TYPE].create({"name": "Surface water", "code": "LM-FIRST-SURF"})
        self.offer(self.parameter, surface_water)
        cabbage = self.env[MODEL_SAMPLE_TYPE].create({"name": "Cabbage", "code": "LM-FIRST-CAB"})
        self.offer(self.other, cabbage)
        # The form helper loads every one-to-many's view, support requests included, which Sales cannot read.
        with Form(self.env[MODEL_SALE_ORDER].with_context(medilab_sales_order=True)) as form:
            form.customer_id = self.customer
            form.expected_collection_date = date.today() + timedelta(days=1)
            lines = assert_instance(form.product_line_ids, O2MProxy)
            with lines.new() as line:
                offered = assert_instance(line.offered_sample_type_ids, M2MProxy)
                self.assertIn(surface_water, offered)
                self.assertIn(self.sample_type, offered)
                line.sample_type_id = surface_water
                line.product_template_id = self.lead_product
                self.assertEqual(line.sample_type_id, surface_water)
                offered = assert_instance(line.offered_sample_type_ids, M2MProxy)
                self.assertIn(self.sample_type, offered)
                self.assertNotIn(cabbage, offered)
            order = form.save()

        self.assertEqual(order.order_line.sample_type_id, surface_water)
