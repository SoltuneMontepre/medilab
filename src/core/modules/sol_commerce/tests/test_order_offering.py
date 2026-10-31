from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_METHOD, MODEL_SAMPLE_TYPE, MODEL_SUBCONTRACTOR


@tagged("post_install", "-at_install")
class TestOrderOffering(OrderCase):
    """Lead and Cadmium are offered on bottled water only; Cabbage offers nothing."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cabbage = cls.env[MODEL_SAMPLE_TYPE].create({"name": "Cabbage", "code": "LM-OFFER"})

    def cabbage_sample(self, order):
        sample = self.make_sample(order, "Cai bap Da Lat")
        sample.sample_type_id = self.cabbage
        return sample

    def test_a_parameter_not_offered_on_the_sample_type_cannot_be_ordered_on_it(self):
        order = self.make_order([(self.lead_product, 1)])
        sample = self.cabbage_sample(order)

        with self.assertRaisesRegex(ValidationError, "is not offered on Cabbage"):
            order._catalog_lines().sample_id = sample

    def test_a_package_needs_each_of_its_parameters_offered(self):
        order = self.make_order([(self.package_product, 1)])
        sample = self.cabbage_sample(order)
        self.offer(self.parameter, self.cabbage)

        with self.assertRaisesRegex(ValidationError, "Cadmium \\(Cd\\) is not offered on Cabbage"):
            order._catalog_lines().sample_id = sample

    def test_changing_the_sample_type_checks_its_lines_again(self):
        order = self.make_quotable_order()
        sample = order._catalog_lines().sample_id

        with self.assertRaisesRegex(ValidationError, "is not offered on Cabbage"):
            sample.sample_type_id = self.cabbage

    def test_an_unavailable_default_is_explained_on_the_line(self):
        subcontractor = self.env[MODEL_SUBCONTRACTOR].create(
            {"name": "Northern Testing Laboratory", "accreditation_expiry": fields.Date.today() + timedelta(days=30)}
        )
        outside = self.env[MODEL_PARAMETER_METHOD].create(
            {"parameter_id": self.parameter.id, "method_id": self.method.id, "subcontractor_id": subcontractor.id}
        )
        self.offer(self.parameter, self.cabbage, outside)
        self.offer(self.parameter, self.cabbage, self.pair)
        subcontractor.accreditation_expiry = fields.Date.today() - timedelta(days=1)
        order = self.make_order([(self.lead_product, 1)])

        order._catalog_lines().sample_id = self.cabbage_sample(order)

        notice = order._catalog_lines().default_way_notice
        self.assertIn("is unavailable", notice)
        self.assertIn(self.pair.display_name, notice)
        self.assertFalse(self.make_quotable_order()._catalog_lines().default_way_notice)
