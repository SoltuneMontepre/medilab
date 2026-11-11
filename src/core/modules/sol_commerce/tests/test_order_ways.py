from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_PARAMETER_METHOD,
    MODEL_SAMPLE_TYPE,
    MODEL_SUBCONTRACTOR,
    MODEL_TESTING_METHOD,
)


@tagged("post_install", "-at_install")
class TestOrderWays(OrderCase):
    """Lead is tested by AAS by default or by ICP-MS on bottled water; the package holds Lead and Cadmium."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        icp = cls.env[MODEL_TESTING_METHOD].create(
            {"code": "TCVN 10643:2014", "name": "Lead by ICP-MS", "field_id": cls.testing_field.id}
        )
        cls.icp = cls.env[MODEL_PARAMETER_METHOD].create(
            {"parameter_id": cls.parameter.id, "method_id": icp.id, "department_id": cls.department.id}
        )
        cls.icp_on_water = cls.offer(cls.parameter, cls.sample_type, cls.icp)

    def lines(self, order):
        lead = order._catalog_lines().filtered(lambda line: line.product_id.product_tmpl_id == self.lead_product)
        package = order._catalog_lines() - lead
        part = package.linked_line_ids.filtered(lambda line: line._own_parameter() == self.parameter)
        return lead, part

    def test_each_parameter_takes_the_default_way_of_its_sample_type(self):
        order = self.make_quotable_order([(self.lead_product, 1), (self.package_product, 1)])

        lead, part = self.lines(order)

        self.assertEqual(lead.sample_type_id, self.sample_type)
        self.assertEqual(lead.parameter_method_id, self.pair)
        self.assertEqual(part.sample_type_id, self.sample_type)
        self.assertEqual(part.parameter_method_id, self.pair)
        self.assertFalse(order._catalog_lines().filtered("linked_line_ids").parameter_method_id)

    def test_a_line_and_a_package_keep_independent_choices(self):
        order = self.make_quotable_order([(self.lead_product, 1), (self.package_product, 1)])
        lead, part = self.lines(order)

        lead.parameter_method_id = self.icp

        self.assertEqual(lead.parameter_method_id, self.icp)
        self.assertEqual(part.parameter_method_id, self.pair)

        order.with_user(self.sales).action_send_quotation()
        values = order.sample_ids._test_request_values()["lines"]
        parameters = [part for line in values for part in line.get("parameters", [line])]
        lead_ways = [item["parameter_method_id"] for item in parameters if item["parameter_id"] == self.parameter.id]
        self.assertEqual(sorted(lead_ways), sorted([self.icp.id, self.pair.id]))

    def test_a_way_that_does_not_test_the_line_is_refused(self):
        order = self.make_quotable_order()

        with self.assertRaisesRegex(ValidationError, "does not test"):
            order._catalog_lines().parameter_method_id = self.other.method_ids[:1]

    def test_an_unavailable_default_is_never_replaced_silently(self):
        cabbage = self.env[MODEL_SAMPLE_TYPE].create({"name": "Cabbage", "code": "LM-WAYS"})
        subcontractor = self.env[MODEL_SUBCONTRACTOR].create(
            {"name": "Northern Testing Laboratory", "accreditation_expiry": fields.Date.today() + timedelta(days=30)}
        )
        outside = self.env[MODEL_PARAMETER_METHOD].create(
            {"parameter_id": self.parameter.id, "method_id": self.method.id, "subcontractor_id": subcontractor.id}
        )
        self.offer(self.parameter, cabbage, outside)
        self.offer(self.parameter, cabbage, self.pair)
        subcontractor.accreditation_expiry = fields.Date.today() - timedelta(days=1)
        order = self.make_order(
            [(self.lead_product, 1)],
            status="claimed",
            user_id=self.sales.id,
            advance_method="cash",
            advance_mode="full",
        )
        sample = self.make_sample(order, "Cai bap Da Lat")
        sample.sample_type_id = cabbage
        line = order._catalog_lines()
        line.sample_id = sample

        self.assertFalse(line.parameter_method_id)
        self.assertEqual(line.offered_method_ids, self.pair)
        with self.assertRaisesRegex(UserError, "Choose a way of testing"):
            order.with_user(self.sales).action_send_quotation()

        line.parameter_method_id = self.pair
        order.with_user(self.sales).action_send_quotation()
        self.assertTrue(order.quotation_ids)

    def test_an_accepted_way_changes_only_through_a_revision(self):
        order = self.sent_order()

        with self.assertRaisesRegex(UserError, "revise it"):
            order._catalog_lines().with_user(self.sales).parameter_method_id = self.icp

        order.with_user(self.sales).action_revise_quotation()
        order._catalog_lines().with_user(self.sales).parameter_method_id = self.icp
        self.assertEqual(order._catalog_lines().parameter_method_id, self.icp)

    def test_catalog_changes_after_acceptance_change_neither_the_order_nor_its_tests(self):
        order = self.make_confirmed_order([(self.lead_product, 1), (self.package_product, 1)])
        lead, part = self.lines(order)

        self.icp_on_water.is_default = True
        self.package.line_ids.filtered(lambda line: line.parameter_id == self.other).unlink()

        self.assertEqual(lead.parameter_method_id, self.pair)
        self.assertEqual(part.parameter_method_id, self.pair)
        self.assertEqual(len(part.linked_line_id.linked_line_ids), 2)
        tests = order.sudo().test_request_id.sample_ids.test_ids
        self.assertEqual(len(tests), 3)
        self.assertEqual(tests.filtered(lambda test: test.parameter_id == self.parameter).accepted_method_id, self.pair)
        self.assertEqual(
            tests.filtered(lambda test: test.parameter_id == self.parameter).parameter_method_id, self.pair
        )

    def test_a_sample_test_keeps_to_its_accepted_way(self):
        order = self.make_confirmed_order()
        test = order.sudo().test_request_id.sample_ids.test_ids

        with self.assertRaisesRegex(ValidationError, "another way needs a revised quotation"):
            test.parameter_method_id = self.icp
        with self.assertRaisesRegex(UserError, "only through a revised quotation"):
            test.accepted_method_id = self.icp

    def test_a_revised_quotation_keeps_the_package_price_and_contents(self):
        order = self.make_quotable_order([(self.package_product, 1)])
        order.with_user(self.sales).action_send_quotation()
        package_line = order._catalog_lines()
        price = package_line.price_unit

        self.package.list_price = 150000
        self.package.line_ids.filtered(lambda line: line.parameter_id == self.other).unlink()
        order.with_user(self.sales).action_revise_quotation()

        self.assertEqual(package_line.price_unit, price)
        self.assertEqual(
            package_line.linked_line_ids.product_id.product_tmpl_id.parameter_id, self.parameter | self.other
        )
        self.assertEqual(package_line.linked_line_ids.parameter_method_id.parameter_id, self.parameter | self.other)

    def test_the_cart_offers_only_what_can_be_ordered(self):
        order = self.make_order([(self.package_product, 1)])
        line = order._catalog_lines()
        cabbage = self.env[MODEL_SAMPLE_TYPE].create({"name": "Cabbage", "code": "LM-CART"})

        self.assertEqual(line._sample_type_choices(), self.sample_type)
        with self.assertRaisesRegex(UserError, "sample types offered"):
            line._set_cart_selection(sample_type_id=cabbage.id)

        line._set_cart_selection(sample_type_id=self.sample_type.id)
        part = line.linked_line_ids.filtered(lambda item: item._own_parameter() == self.parameter)
        self.assertEqual(part.sample_type_id, self.sample_type)
        part._set_cart_selection(parameter_method_id=self.icp.id)
        self.assertEqual(part.parameter_method_id, self.icp)
        with self.assertRaisesRegex(UserError, "ways of testing offered"):
            part._set_cart_selection(parameter_method_id=self.other.method_ids[:1].id)
