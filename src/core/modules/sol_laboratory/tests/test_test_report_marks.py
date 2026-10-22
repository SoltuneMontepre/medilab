from odoo.tests import tagged

from .dispatch_case import DISPATCH_PERMISSIONS
from .report_case import ReportCase
from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_METHOD, MODEL_SUBCONTRACTOR
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REPORT_REPORT

NOTE_VI = "(TP) Chỉ tiêu do nhà thầu phụ thực hiện"
NOTE_EN = "Tested by a subcontractor"


@tagged("post_install", "-at_install")
class TestTestReportMarks(ReportCase):
    """Northern tests lead for the laboratory; arsenic is tested in-house."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        northern = cls.env[MODEL_SUBCONTRACTOR].create({"name": "Northern Testing Laboratory"})
        cls.northern_way = cls.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": cls.parameter.id,
                "method_id": cls.method.id,
                "unit_id": cls.unit.id,
                "subcontractor_id": northern.id,
            }
        )
        cls.grant(cls.head, *DISPATCH_PERMISSIONS)

    def html(self, report):
        return self.env["ir.actions.report"]._render_qweb_html(TEST_REPORT_REPORT, report.ids)[0].decode()

    def complete_outsourced_and_in_house(self):
        """Lead is outsourced to Northern and arsenic tested in-house; both results are approved."""
        self.test.outsourcing_suggested = True
        dispatch = self.as_person(self.test, self.head)._accept_outsourcing(self.northern_way)
        dispatch.write({"sent_date": "2026-10-12", "expected_date": "2026-10-16", "courier_id": self.courier.id})
        dispatch.action_send()
        arsenic = self.add_test()
        self.complete()
        self.complete(test=arsenic)
        return arsenic

    def test_a_subcontracted_result_is_marked_and_the_mark_is_explained(self):
        arsenic = self.complete_outsourced_and_in_house()

        printed = self.html(self.report())

        self.assertIn(f"{self.parameter.name} (TP)", printed)
        self.assertNotIn(f"{arsenic.parameter_id.name} (TP)", printed)
        self.assertIn(f"{NOTE_VI} / {NOTE_EN}", printed)

    def test_an_english_report_marks_a_subcontracted_result_in_english(self):
        self.request.report_language = "en"
        self.complete_outsourced_and_in_house()

        printed = self.html(self.report())

        self.assertIn(f"{self.parameter.name} (S)", printed)
        self.assertIn(f"(S) {NOTE_EN}", printed)
        self.assertNotIn("(TP)", printed)

    def test_a_report_without_subcontracted_results_has_no_note(self):
        self.complete()

        printed = self.html(self.report())

        self.assertNotIn(NOTE_EN, printed)
        self.assertNotIn(NOTE_VI, printed)
