from freezegun import freeze_time

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .result_case import ResultCase
from .scheduling_case import MONDAY


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestNegativeResults(ResultCase):
    def test_a_negative_number_is_refused_unless_the_way_of_testing_allows_it(self):
        with self.assertRaises(ValidationError):
            self.enter(value=-0.002)

        self.pair.allows_negative = True

        self.assertEqual(self.enter(value=-0.002).value, -0.002)

    def test_a_result_cannot_be_changed_to_a_negative_number(self):
        result = self.enter()

        with self.assertRaises(ValidationError):
            self.as_person(result, self.tester).value = -0.002

    def test_a_measurement_below_the_lod_is_entered_as_a_text(self):
        result = self.enter(value=0, value_text="< LOD")

        self.assertEqual(result.value_display, "< LOD")
