from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_PRODUCT_TEMPLATE
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MEASUREMENT_UNIT,
    MODEL_PARAMETER_METHOD,
    MODEL_RES_LANG,
    MODEL_SAMPLING_REQUIREMENT,
    MODEL_TEST_REQUEST,
    MODEL_TESTING_METHOD,
)


@tagged("post_install", "-at_install")
class TestExpectedSampling(OrderCase):
    """Lead needs 500 mL in an acidified polyethylene bottle; Cadmium is tested by its own method, which needs 250 mL in
    a chilled glass bottle. The package holds Lead and Cadmium."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ml = cls.env[MODEL_MEASUREMENT_UNIT].create({"name": "mL", "category_id": cls.category.id})
        cls.cadmium_method = cls.env[MODEL_TESTING_METHOD].create(
            {"code": "TCVN 6193:1996", "name": "Cadmium by AAS", "field_id": cls.testing_field.id}
        )
        cls.cadmium_way = cls.env[MODEL_PARAMETER_METHOD].create(
            {"parameter_id": cls.other.id, "method_id": cls.cadmium_method.id, "department_id": cls.department.id}
        )
        cls.offer(cls.other, cls.sample_type, cls.cadmium_way, is_default=True)
        cls.cadmium_product = cls.env[MODEL_PRODUCT_TEMPLATE].search([("parameter_id", "=", cls.other.id)], limit=1)
        cls.lead_requirement = cls.require(cls.method, 500, "Polyethylene bottle", "Acidified with HNO3")
        cls.cadmium_requirement = cls.require(cls.cadmium_method, 250, "Sterile glass bottle", "Chilled at 2-8 °C")

    @classmethod
    def require(cls, method, amount, container, preservation, unit=None):
        return cls.env[MODEL_SAMPLING_REQUIREMENT].create(
            {
                "method_id": method.id,
                "sample_type_id": cls.sample_type.id,
                "amount": amount,
                "unit_id": (unit or cls.ml).id,
                "container_type": container,
                "preservation": preservation,
            }
        )

    def entry(self, order):
        entries = order._expected_sampling()
        self.assertEqual(len(entries), 1)
        return entries[0]

    def test_quantities_2_and_3_in_two_groups_expect_3_objects_and_6_samples(self):
        order = self.make_quotable_order([(self.lead_product, 2), (self.cadmium_product, 3)])

        entry = self.entry(order)

        self.assertEqual(entry["objects"], 3)
        self.assertEqual(entry["expected"], 6)
        self.assertEqual(
            [(group["container_type"], group["amounts"][0][0]) for group in entry["groups"]],
            [("Polyethylene bottle", 500), ("Sterile glass bottle", 250)],
        )
        self.assertIn("o_medilab_expected", order.expected_sampling_html)

    def test_cart_lines_not_on_a_sample_are_counted_by_sample_type(self):
        order = self.make_order([(self.lead_product, 2), (self.cadmium_product, 3)])
        order.order_line.sample_type_id = self.sample_type

        entry = self.entry(order)

        self.assertEqual(entry["name"], self.sample_type.name)
        self.assertEqual((entry["objects"], entry["expected"]), (3, 6))

    def test_package_parameters_use_their_retained_ways(self):
        order = self.make_quotable_order([(self.package_product, 3)])
        self.assertEqual(self.entry(order)["expected"], 6)

        cadmium = order._catalog_lines().linked_line_ids.filtered(lambda line: line._own_parameter() == self.other)
        cadmium.parameter_method_id = self.other.method_ids - self.cadmium_way

        entry = self.entry(order)
        self.assertEqual(entry["objects"], 3)
        self.assertEqual(entry["expected"], 3)
        self.assertEqual(entry["groups"][0]["amounts"], [(500, self.ml)])

    def test_same_container_and_preservation_add_their_amounts(self):
        self.cadmium_requirement.write(
            {"container_type": "polyethylene  BOTTLE", "preservation": "acidified with HNO3"}
        )
        order = self.make_quotable_order([(self.lead_product, 2), (self.cadmium_product, 3)])

        entry = self.entry(order)

        self.assertEqual(entry["expected"], 3)
        self.assertEqual(entry["groups"][0]["amounts"], [(750, self.ml)])

    def test_different_container_or_preservation_form_separate_groups(self):
        order = self.make_quotable_order([(self.lead_product, 1), (self.cadmium_product, 1)])
        for values in ({"container_type": "Polyethylene bottle"}, {"preservation": "Acidified with HNO3"}):
            self.cadmium_requirement.write(
                {"container_type": "Sterile glass bottle", "preservation": "Chilled at 2-8 °C", **values}
            )

            self.assertEqual(len(self.entry(order)["groups"]), 2)

    def test_amounts_in_other_units_are_listed_apart_in_their_group(self):
        grams = self.env[MODEL_MEASUREMENT_UNIT].create({"name": "g", "category_id": self.category.id})
        self.cadmium_requirement.write(
            {"container_type": "Polyethylene bottle", "preservation": "Acidified with HNO3", "unit_id": grams.id}
        )
        order = self.make_quotable_order([(self.lead_product, 2), (self.cadmium_product, 1)])

        entry = self.entry(order)

        self.assertEqual(entry["expected"], 2)
        self.assertEqual(entry["groups"][0]["amounts"], [(500, self.ml), (250, grams)])

    def test_a_method_without_requirement_forms_no_group_and_is_listed(self):
        self.cadmium_requirement.unlink()
        order = self.make_quotable_order([(self.lead_product, 2), (self.cadmium_product, 3)])

        entry = self.entry(order)

        self.assertEqual(entry["missing"], self.cadmium_method)
        self.assertEqual(entry["expected"], 3)
        order.with_user(self.sales).action_send_quotation()
        kept = order._latest_quotation().sampling_ids
        self.assertEqual(kept.filtered(lambda row: not row.group_number).method_ids, self.cadmium_method)
        self.assertEqual(self.entry(order)["missing"], self.cadmium_method)

    def test_accepted_quotation_keeps_its_sampling_when_the_catalog_changes(self):
        self.env[MODEL_RES_LANG]._activate_lang("vi_VN")
        self.lead_requirement.update_field_translations("container_type", {"vi_VN": "Chai PE"})
        order = self.make_quotable_order([(self.lead_product, 2), (self.cadmium_product, 3)])
        order.with_user(self.sales).action_send_quotation()
        self.pay_advance(order)
        quotation = order._latest_quotation()
        self.assertEqual(quotation.status, "accepted")

        self.lead_requirement.write({"amount": 1000, "container_type": "Glass jar"})

        self.assertEqual(
            sorted(quotation.sampling_ids.mapped(lambda row: (row.container_type, row.amount))),
            [("Polyethylene bottle", 500), ("Sterile glass bottle", 250)],
        )
        self.assertEqual(self.entry(order)["groups"][0]["container_type"], "Polyethylene bottle")
        order.with_user(self.sales).action_confirm_order()
        sample = self.env[MODEL_TEST_REQUEST].browse(order.test_request_id.id).sample_ids
        self.assertEqual(sample.expected_sample_count, 6)
        self.assertEqual(
            sorted(sample.expected_sampling_ids.mapped(lambda row: (row.container_type, row.amount, row.objects))),
            [("Polyethylene bottle", 500, 3), ("Sterile glass bottle", 250, 3)],
        )
        kept = sample.expected_sampling_ids.filtered(lambda row: row.amount == 500)
        self.assertEqual(kept.with_context(lang="vi_VN").container_type, "Chai PE")

    def test_a_revision_recalculates_from_the_catalog(self):
        order = self.make_quotable_order([(self.lead_product, 1)])
        order.with_user(self.sales).action_send_quotation()
        self.lead_requirement.amount = 1000
        self.assertEqual(self.entry(order)["groups"][0]["amounts"], [(500, self.ml)])

        order.with_user(self.sales).action_revise_quotation()

        self.assertEqual(self.entry(order)["groups"][0]["amounts"], [(1000, self.ml)])
