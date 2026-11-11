from datetime import timedelta

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_REGULATION,
    MODEL_SAMPLE,
    MODEL_SAMPLE_TYPE,
    MODEL_TEST_REQUEST,
)


@tagged("post_install", "-at_install")
class TestRegulationSelection(RequestCase):
    """A regulation on the sample's type, in force on no fixed dates, and a narrower type of that type."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = cls.env[MODEL_SAMPLE]._company_today()
        cls.regulation = cls.env[MODEL_REGULATION].create(
            {"code": "QCVN 6-1:2010/BYT", "name": "Bottled drinking waters", "sample_type_ids": cls.sample_type.ids}
        )
        cls.still_water = cls.env[MODEL_SAMPLE_TYPE].create({"name": "Still water", "parent_id": cls.sample_type.id})

    def test_a_regulation_in_force_on_its_last_valid_day_is_chosen(self):
        self.regulation.write({"valid_from": self.today, "valid_until": self.today})
        self.assertFalse(self.sample.regulation_notice)

        self.sample.regulation_id = self.regulation

        self.assertEqual(self.sample.regulation_id, self.regulation)
        self.assertFalse(self.sample.regulation_notice)

    def test_a_regulation_applies_to_the_narrower_types_of_its_types(self):
        self.sample.write({"sample_type_id": self.still_water.id, "regulation_id": self.regulation.id})

        self.assertEqual(self.sample.regulation_id, self.regulation)

    def test_a_regulation_that_cannot_be_chosen_today_is_refused(self):
        other = self.env[MODEL_SAMPLE_TYPE].create({"name": "Surface water"})
        for code, values in (
            ("Not in force yet", {"valid_from": self.today + timedelta(days=1)}),
            ("No longer in force", {"valid_until": self.today - timedelta(days=1)}),
            ("Archived", {"active": False}),
            ("For another sample type", {"sample_type_ids": other.ids}),
        ):
            regulation = self.regulation.copy({"code": code, **values})
            with self.subTest(code), self.assertRaises(ValidationError):
                self.sample.regulation_id = regulation

    def test_a_sample_type_outside_the_scope_of_its_regulation_is_refused(self):
        self.sample.regulation_id = self.regulation

        with self.assertRaises(ValidationError):
            self.sample.sample_type_id = self.env[MODEL_SAMPLE_TYPE].create({"name": "Surface water"})

    def test_a_sample_keeps_a_regulation_that_expires_and_says_so(self):
        self.sample.regulation_id = self.regulation

        self.regulation.valid_until = self.today - timedelta(days=1)

        self.assertEqual(self.sample.regulation_id, self.regulation)
        self.assertIn("QCVN 6-1:2010/BYT is no longer in force", self.sample.regulation_notice or "")

    def test_a_confirmed_order_keeps_the_regulation_the_customer_accepted(self):
        self.regulation.valid_until = self.today - timedelta(days=1)

        request = self.env[MODEL_TEST_REQUEST].create_from_order(
            self.customer,
            [
                {
                    "customer_sample_name": "Lavie bottled water 1 L",
                    "sample_type_id": self.sample_type.id,
                    "physical_state": "liquid",
                    "regulation_id": self.regulation.id,
                }
            ],
        )

        self.assertEqual(request.sample_ids.regulation_id, self.regulation)
        self.assertTrue(request.sample_ids.regulation_notice)
        with self.assertRaises(ValidationError):
            self.create_request().sample_ids.regulation_id = self.regulation
