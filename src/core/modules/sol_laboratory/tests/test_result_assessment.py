from freezegun import freeze_time

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .result_case import ResultCase
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_CHANGE_REQUEST,
    MODEL_PARAMETER_METHOD,
    MODEL_SAMPLE_TYPE,
    MODEL_TESTING_METHOD,
)


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestResultAssessment(ResultCase):
    """The lead way of testing detects 0.002 mg/g and quantifies 0.006 mg/g on the sample's type."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.applicability.write({"lod": 0.002, "loq": 0.006})

    def narrower_type(self):
        """Move the sample to a narrower type with its own way of testing, on which the regulation sets no limit."""
        still_water = self.env[MODEL_SAMPLE_TYPE].create({"name": "Still water", "parent_id": self.sample_type.id})
        self.offer(self.parameter, still_water)
        self.sample.sample_type_id = still_water

    def test_a_result_copies_its_way_sample_type_unit_and_detection_limits(self):
        result = self.enter(value=0.0125, value_decimals=4)

        self.assertEqual(result.parameter_method_id, self.pair)
        self.assertEqual(result.sample_type_id, self.sample_type)
        self.assertEqual(result.unit_id, self.unit)
        self.assertEqual((result.lod, result.loq), (0.002, 0.006))
        self.assertEqual((result.value, result.value_decimals), (0.0125, 4))
        self.assertEqual(result.regulation_id, self.sample.regulation_id)
        self.assertTrue(result.comparison_requested)

    def test_catalog_edits_do_not_change_what_a_result_copied(self):
        result = self.enter()
        icp_ms = self.env[MODEL_TESTING_METHOD].create(
            {"code": "TCVN 10912:2015", "name": "Lead by ICP-MS", "field_id": self.testing_field.id}
        )
        other = self.env[MODEL_PARAMETER_METHOD].create(
            {"parameter_id": self.parameter.id, "method_id": icp_ms.id, "department_id": self.department.id}
        )

        self.applicability.write({"lod": 0.004, "loq": 0.012, "result_decimals": 1})
        self.limit.write({"max_value": 0.05, "decimals": 1})
        self.offer(self.parameter, self.sample_type, way=other, is_default=True)
        self.env.flush_all()
        result.invalidate_recordset()

        self.assertEqual(result.parameter_method_id, self.pair)
        self.assertEqual((result.lod, result.loq, result.value_decimals), (0.002, 0.006, 3))
        self.assertEqual((result.limit_max, result.limit_decimals, result.limit_unit_id), (0.01, 0, self.unit))

    def test_a_tester_cannot_rewrite_what_a_result_copied(self):
        result = self.enter()

        for values in ({"lod": 0.1}, {"parameter_method_id": False}, {"comparison_requested": False}):
            with self.subTest(values=values), self.assertRaises(UserError):
                self.as_person(result, self.tester).write(values)

    def test_an_absent_lod_stays_absent_and_zero_stays_zero(self):
        self.applicability.write({"lod": False, "loq": 0.0})

        result = self.enter()

        self.assertIs(result.lod, False)
        self.assertEqual(result.loq, 0.0)
        self.assertIsNot(result.loq, False)

    def test_a_result_outside_the_requested_comparison_takes_no_conclusion(self):
        test = self.add_test()

        result = self.enter(test=test)

        self.assertFalse(result.comparison_requested)
        self.assertFalse(result.limit_missing)
        with self.assertRaises(ValidationError):
            self.as_person(result, self.tester).conclusion = "pass"
        self.send(result)
        self.assertEqual(result.status, "requested")

    def test_a_sample_without_a_regulation_needs_no_conclusion(self):
        self.sample.regulation_id = False

        result = self.enter()

        self.assertFalse(result.regulation_id)
        self.assertFalse(result.comparison_requested)
        self.send(result)
        self.assertEqual(result.status, "requested")

    def test_a_missing_exact_type_limit_is_assessed_only_as_insufficient_basis(self):
        self.narrower_type()

        result = self.enter(conclusion=False)

        self.assertTrue(result.comparison_requested)
        self.assertTrue(result.limit_missing)
        for conclusion in ("pass", "fail"):
            with self.subTest(conclusion=conclusion), self.assertRaises(ValidationError):
                self.as_person(result, self.tester).conclusion = conclusion
        with self.assertRaises(UserError):
            self.send(result)
        self.as_person(result, self.tester).conclusion = "insufficient"
        self.send(result)
        self.assertEqual(result.status, "requested")

    def test_a_text_result_is_never_passed_by_inference(self):
        result = self.enter(value=0, value_text="Not detected", conclusion=False)

        self.assertFalse(result.conclusion)
        with self.assertRaises(UserError):
            self.send(result)
        self.as_person(result, self.tester).conclusion = "insufficient"
        self.send(result)
        self.assertEqual(result.conclusion, "insufficient")

    def test_a_value_below_the_lod_or_loq_suggests_a_text_with_the_copied_threshold(self):
        cases = ((0.001, "<0.002 mg/g (below LOD)"), (0.004, "<0.006 mg/g (below LOQ)"), (0.008, False))
        for value, suggestion in cases:
            with self.subTest(value=value):
                self.assertEqual(self.enter(value=value).value_suggestion, suggestion)

    def test_confirming_the_suggested_text_keeps_the_measured_value(self):
        result = self.enter(value=0.001)

        self.as_person(result, self.tester).action_use_value_suggestion()

        self.assertEqual(result.value_text, "<0.002 mg/g (below LOD)")
        self.assertEqual(result.value_display, "<0.002 mg/g (below LOD)")
        self.assertEqual(result.value, 0.001)
        self.assertFalse(result.value_suggestion)
        self.assertEqual(result.conclusion, "pass", "Confirming the text leaves the tester's assessment as it was.")

    def test_a_value_above_the_loq_has_no_text_to_confirm(self):
        result = self.enter(value=0.008)

        with self.assertRaises(UserError):
            self.as_person(result, self.tester).action_use_value_suggestion()

    def test_a_new_version_keeps_what_the_replaced_one_copied(self):
        result = self.enter()
        self.send(result)
        self.approve(result)
        self.applicability.lod = 0.004

        version = result._new_version(self.env[MODEL_CHANGE_REQUEST].new({"requested_change": "Fix the value"}))

        self.assertEqual((version.parameter_method_id, version.lod), (self.pair, 0.002))
        self.assertTrue(version.comparison_requested)
        self.assertEqual(version.conclusion, "pass")
