from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .result_case import ResultCase
from odoo.addons.sol_laboratory.constants.models import MODEL_MEASUREMENT_UNIT, MODEL_TEST_RESULT
from odoo.addons.sol_laboratory.constants.settings import RESULT_CHECK_MARGIN_PARAMETER, RESULT_CHECK_MINIMUM_PARAMETER


def text(value) -> str:
    """The warning a text field holds; empty when it holds none."""
    return value if isinstance(value, str) else ""


# Lead values of past approved results in mg/g: their mean is 0.005 and their standard deviation about 0.0003.
PAST_VALUES = (0.0045, 0.0048, 0.005, 0.0052, 0.0055, 0.0047, 0.0053, 0.005, 0.0049, 0.0051)


class SanityCheckCase(ResultCase):
    """The lead result is compared with QCVN 01-1:2018/BYT, which allows at most 0.01 mg/g, and with the approved results
    of its way of testing on bottled water."""

    def approved_results(self, values=PAST_VALUES, **extra):
        """Approved lead results of earlier measurements of the same way of testing on the same sample type."""
        # One at a time: each result entered becomes the reported one.
        for value in values:
            self.env[MODEL_TEST_RESULT].create(
                {"sample_test_id": self.test.id, "value": value, "status": "approved", **extra}
            )


@tagged("post_install", "-at_install")
class TestResultSanityCheck(SanityCheckCase):
    def test_a_value_far_from_the_approved_results_warns_and_the_warning_stays_once_sent(self):
        self.approved_results()
        result = self.enter(value=0.0062)

        self.assertIn("standard deviations", text(result.check_preview))
        self.assertIn("0.005 mg/g", text(result.check_preview))
        self.assertIn("10", text(result.check_preview))
        self.assertFalse(result.check_warning)
        self.send(result)

        self.assertEqual(result.status, "requested")
        self.assertIn("standard deviations", text(result.check_warning))
        self.assertFalse(result.check_preview)
        self.assertEqual(self.as_person(result, self.head).check_warning, result.check_warning)

    def test_the_warning_sent_reads_in_the_language_of_whoever_opens_the_result(self):
        self.env["res.lang"]._activate_lang("vi_VN")
        self.env["ir.module.module"]._load_module_terms(["sol_laboratory"], ["vi_VN"], overwrite=True)
        self.approved_results()
        result = self.enter(value=0.0062)

        self.send(result)

        self.assertIn("standard deviations", text(result.with_context(lang="en_US").check_warning))
        self.assertIn("độ lệch chuẩn", text(result.with_context(lang="vi_VN").check_warning))

    def test_a_value_close_to_the_approved_results_does_not_warn(self):
        self.approved_results()

        result = self.enter(value=0.0051)

        self.assertFalse(result.check_preview)
        self.send(result)
        self.assertFalse(result.check_warning)

    def test_with_fewer_approved_results_than_the_minimum_only_the_limit_is_checked(self):
        self.approved_results(PAST_VALUES[:9])

        far = self.enter(value=0.0062)
        self.assertFalse(far.check_preview)
        near_limit = self.enter(value=0.0095)
        self.assertIn("0.0095 mg/g is within 10% of the regulation limit 0.01 mg/g", text(near_limit.check_preview))
        self.assertNotIn("standard deviations", text(near_limit.check_preview))

    def test_the_minimum_count_and_the_margin_are_system_parameters(self):
        parameters = self.env["ir.config_parameter"].sudo()
        parameters.set_str(RESULT_CHECK_MINIMUM_PARAMETER, "5")
        parameters.set_str(RESULT_CHECK_MARGIN_PARAMETER, "0")
        self.approved_results(PAST_VALUES[:5])

        result = self.enter(value=0.0095)

        self.assertIn("standard deviations", text(result.check_preview))
        self.assertNotIn("regulation limit", text(result.check_preview))

    def test_a_value_just_above_the_limit_warns_too(self):
        result = self.enter(value=0.0105, conclusion="fail")

        self.assertIn("regulation limit", text(result.check_preview))

    def test_a_value_exactly_on_the_margin_warns(self):
        # 0.009 is exactly 10% below 0.01, which floating-point subtraction puts just past the margin.
        result = self.enter(value=0.009)

        self.assertIn("0.009 mg/g is within 10% of the regulation limit 0.01 mg/g", text(result.check_preview))

    def test_a_value_far_above_the_limit_warns_that_it_is_above_and_cannot_pass(self):
        result = self.enter(value=0.03)

        self.assertIn("0.030 mg/g is above the regulation limit 0.01 mg/g", text(result.check_preview))
        with self.assertRaises(UserError):
            self.send(result)
        self.assertEqual(result.status, "none")
        self.as_person(result, self.tester).conclusion = "fail"
        self.send(result)
        self.assertEqual(result.status, "requested")
        self.assertIn("above the regulation limit", text(result.check_warning))

    def test_a_value_below_the_minimum_warns_and_cannot_pass(self):
        self.limit.write({"min_set": True, "min_value": 0.002})

        result = self.enter(value=0.001)

        self.assertIn("0.001 mg/g is below the regulation limit 0.002 mg/g", text(result.check_preview))
        with self.assertRaises(UserError):
            self.send(result)

    def test_a_value_on_the_limit_still_passes(self):
        result = self.enter(value=0.01)

        self.send(result)

        self.assertEqual(result.status, "requested")

    def test_a_limit_in_another_unit_of_the_same_category_is_converted(self):
        micrograms = self.env[MODEL_MEASUREMENT_UNIT].create(
            {"name": "ug/g", "category_id": self.category.id, "factor": 0.001}
        )
        self.limit.write({"unit_id": micrograms.id, "max_value": 10})

        result = self.enter(value=0.0095)

        self.assertIn("regulation limit 10 ug/g", text(result.check_preview))

    def test_a_text_result_and_approved_text_results_are_not_checked(self):
        self.approved_results(value_text="Not detected")
        self.approved_results(PAST_VALUES[:9])

        text = self.enter(value_text="< 0.002 mg/g (below LOD)")
        self.assertFalse(text.check_preview)
        far = self.enter(value=0.0062)
        self.assertFalse(far.check_preview)

    def test_the_warning_names_no_customer_or_sample(self):
        self.approved_results()

        result = self.enter(value=0.0095)

        warning = text(result.check_preview)
        self.assertTrue(warning)
        for name in filter(None, (self.customer.name, self.sample.code, self.sample.customer_sample_name)):
            self.assertNotIn(name, warning)

    def test_the_result_form_warns_the_tester_while_they_enter_the_value(self):
        results = self.env[MODEL_TEST_RESULT].with_user(self.tester.user_id)
        form = Form(results.with_context(default_sample_test_id=self.test.id))
        form.value = 0.0095
        form.conclusion = "pass"

        self.assertIn("regulation limit", text(form.check_preview))
        result = form.save()
        self.assertFalse(result.check_warning)
