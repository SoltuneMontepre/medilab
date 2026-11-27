import os
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .report_case import ReportCase
from odoo.addons.sol_laboratory.constants.laboratory_editing import INTERNAL_URL_VARIABLE
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REPORT_TEMPLATE_CHANGE
from odoo.addons.sol_laboratory.constants.report_templates import (
    CANDIDATE_BUILT_IN,
    CANDIDATE_ISSUED,
    CANDIDATE_PRINT_CONTEXT,
    CANDIDATE_REVIEW,
)


@tagged("post_install", "-at_install")
class TestReportBuiltInPdf(ReportCase):
    """On an installation without ONLYOFFICE, Odoo's own report renders the PDF the lab head reviews, signs and issues,
    and template versions do not apply."""

    def setUp(self):
        super().setUp()
        self.enterContext(patch.dict(os.environ))
        os.environ.pop(INTERNAL_URL_VARIABLE, None)
        self.complete()

    def prepared(self):
        self.run_preparation()
        report = self.report()
        return report, report._candidate()

    def test_the_job_prepares_the_pdf_with_the_built_in_report_and_the_reserved_number(self):
        report, candidate = self.prepared()

        self.assertEqual((candidate.status, candidate.origin), (CANDIDATE_REVIEW, CANDIDATE_BUILT_IN))
        self.assertFalse(candidate.template_version_id or candidate.docx_version_id or report.draft_file_id)
        self.conversion.assert_not_called()
        self.health_check.assert_not_called()
        self.assertRegex(report.code or "", r"^PKQ\.")
        self.assertEqual(candidate.report_number, report.code)
        self.assertTrue(bytes(candidate.attachment_id.raw).startswith(b"%PDF"))
        self.assertTrue(report._print_draft_mark())
        self.assertFalse(report.with_context(**{CANDIDATE_PRINT_CONTEXT: True})._print_draft_mark())
        self.assertTrue(report.candidate_current)
        self.assertFalse(report.uses_templates)

    def test_the_lab_head_signs_and_issues_the_built_in_pdf(self):
        report, candidate = self.prepared()

        self.as_person(report, self.lab_head).action_sign()

        self.assertEqual(report.status, "issued")
        self.assertEqual(candidate.status, CANDIDATE_ISSUED)
        self.assertEqual(bytes(report.attachment_id.raw), bytes(candidate.attachment_id.raw))
        self.assertEqual(len(self.issued_messages(report)), 1)

    def test_a_built_in_pdf_out_of_date_with_the_approved_data_cannot_be_signed(self):
        report, _candidate = self.prepared()
        self.customer.name = "An Phu Water Joint Stock Company"

        self.assertFalse(report.candidate_current)
        with self.assertRaises(UserError):
            self.as_person(report, self.lab_head).action_sign()
        self.assertEqual(report.status, "draft")

    def test_template_versions_apply_only_with_onlyoffice(self):
        report, _candidate = self.prepared()
        version = self.available_template().version_ids

        with self.assertRaisesRegex(UserError, "only on an installation with ONLYOFFICE"):
            self.as_person(self.env[MODEL_TEST_REPORT_TEMPLATE_CHANGE], self.lab_head).create(
                {"report_id": report.id, "template_version_id": version.id}
            ).action_apply()
