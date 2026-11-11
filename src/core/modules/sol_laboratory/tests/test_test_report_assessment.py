from odoo.tests import tagged

from .report_case import ReportCase
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TYPE


@tagged("post_install", "-at_install")
class TestTestReportAssessment(ReportCase):
    """The report of the lead sample, compared with QCVN 01-1:2018/BYT, prints in English."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.request.report_language = "en"
        cls.limit.decimals = 2

    def printed(self):
        [sample] = self.report()._print_samples()
        return sample

    def test_a_passing_comparison_prints_its_limit_and_assessment_within_the_compared_scope(self):
        arsenic = self.add_test()
        self.complete()
        self.complete(test=arsenic)

        sample = self.printed()

        self.assertEqual(sample["conclusion"], "Meets QCVN 01-1:2018/BYT for the compared parameters")
        lead, outside = sample["rows"]
        self.assertEqual((lead["limit"], lead["conclusion"]), ("≤ 0.01", "Pass"))
        self.assertEqual((outside["limit"], outside["conclusion"]), ("", ""))

    def test_any_failure_fails_the_compared_scope(self):
        self.complete(conclusion="fail")

        self.assertEqual(self.printed()["conclusion"], "Does not meet QCVN 01-1:2018/BYT for the compared parameters")

    def test_a_missing_limit_prints_as_missing_and_concludes_insufficient_basis(self):
        still_water = self.env[MODEL_SAMPLE_TYPE].create({"name": "Still water", "parent_id": self.sample_type.id})
        self.offer(self.parameter, still_water)
        self.sample.sample_type_id = still_water
        self.complete(conclusion="insufficient")

        sample = self.printed()

        self.assertEqual(sample["conclusion"], "Insufficient basis to conclude against QCVN 01-1:2018/BYT")
        [row] = sample["rows"]
        self.assertEqual((row["limit"], row["conclusion"]), ("No limit for this sample type", "Insufficient Basis"))

    def test_a_sample_without_a_requested_comparison_prints_no_limit_or_conclusion(self):
        self.sample.regulation_id = False
        self.complete()

        sample = self.printed()

        self.assertEqual(sample["conclusion"], "")
        self.assertEqual(list(sample["rows"][0]), ["parameter", "result", "unit", "method"])

    def test_a_confirmed_below_lod_text_prints_with_its_copied_threshold(self):
        self.applicability.lod = 0.002
        result = self.enter(value=0.001)
        self.as_person(result, self.tester).action_use_value_suggestion()
        self.send(result)
        self.approve(result)

        self.assertEqual(self.printed()["rows"][0]["result"], "<0.002 mg/g (below LOD)")
