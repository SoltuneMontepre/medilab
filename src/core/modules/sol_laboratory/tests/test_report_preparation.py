from datetime import datetime

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .report_case import PDF
from .report_preparation_case import ReportPreparationCase
from odoo.addons.sol_laboratory.constants.laboratory_files import EDITED_ONLINE, GENERATED, PERMISSION_DENIED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_JOB_ITEM,
    MODEL_LABORATORY_CONTENT,
    MODEL_LABORATORY_DEVICE,
    MODEL_REPORT_TEMPLATE_VERSION,
    MODEL_TEST_REPORT_TEMPLATE_CHANGE,
)
from odoo.addons.sol_laboratory.constants.report_templates import CANDIDATE_OBSOLETE, CANDIDATE_REVIEW
from odoo.addons.sol_laboratory.services import report_docx
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.report_conversion import ConversionUnavailable
from odoo.addons.sol_laboratory.tests.assertions import assert_instance


@tagged("post_install", "-at_install")
class TestReportPreparation(ReportPreparationCase):
    def prepared(self):
        """The completed request's report, once the job prepared its PDF, and that PDF."""
        self.run_preparation()
        report = self.report()
        return report, report._candidate()

    def change_template(self, report, version, person):
        wizard = self.as_person(self.env[MODEL_TEST_REPORT_TEMPLATE_CHANGE], person).create(
            {"report_id": report.id, "template_version_id": version.id}
        )
        wizard.action_apply()

    def test_a_completed_request_waits_for_its_pdf_until_the_job_prepares_it(self):
        report = self.report()
        self.assertFalse(report.candidate_ids)
        self.assertTrue(report.pdf_preparable)
        self.assertFalse(report.has_candidate)
        with self.assertRaisesRegex(UserError, "Prepare the report's PDF"):
            self.as_person(report, self.lab_head).action_sign()

        self.run_preparation()
        self.run_preparation()

        self.assertEqual(len(report.candidate_ids), 1)
        self.assertTrue(report.has_candidate and report.candidate_current)
        items = self.env[MODEL_JOB_ITEM].search(
            [("document_model", "=", report._name), ("document_id", "=", report.id)]
        )
        self.assertEqual(items.mapped("status"), ["done"])

    def test_draft_is_generated_from_the_available_template_and_approved_results(self):
        report, _candidate = self.prepared()
        draft = report.draft_ids
        self.assertEqual(draft.template_version_id, self.template.version_ids)
        self.assertEqual(draft.docx_version_id.source, GENERATED)
        self.assertEqual(draft.result_ids, report.result_ids)
        printed = report_docx.bindings(self.docx_of(draft.docx_version_id))
        self.assertIn(self.request.code, printed["request_code"][0])
        self.assertIn(self.sample.code, printed["samples"][0])
        self.assertEqual(printed["report_number"], [""])

    def test_preparing_reserves_the_number_and_freezes_the_candidate(self):
        report, candidate = self.prepared()
        self.assertEqual(candidate.status, CANDIDATE_REVIEW)
        self.assertRegex(report.code or "", r"^PKQ\.")
        self.assertEqual(report.status, "draft")
        self.assertEqual(candidate.report_number, report.code)
        self.assertEqual(candidate.template_version_id, self.template.version_ids)
        self.assertEqual(candidate.docx_version_id, report.draft_file_id.current_version_id)
        self.assertEqual(bytes(candidate.attachment_id.raw), PDF)
        self.assertEqual(len(candidate.sha256 or ""), 64)
        self.assertEqual(candidate.result_ids, report.result_ids)
        self.assertTrue(candidate._is_current())
        printed = report_docx.bindings(self.docx_of(candidate.docx_version_id))
        self.assertEqual(printed["report_number"], [report.code])
        self.assertTrue(report.has_candidate and report.candidate_current)

    def test_nobody_edits_the_draft(self):
        report, _candidate = self.prepared()
        file = report.draft_file_id
        users = (
            self.courier.user_id,
            self.lab_head.user_id,
            self.template_admin.user_id,
            self.env.ref("base.user_admin"),
        )
        for user in users:
            with self.subTest(user=user.login), self.assertRaises(LaboratoryFileError) as refused:
                file.with_user(user)._check_file_access("write")
            self.assertEqual(refused.exception.code, PERMISSION_DENIED)
        # A save of an editor, from the browser or a computer, is refused too.
        content = self.env[MODEL_LABORATORY_CONTENT]._store_bytes(b"PK edited")
        with self.assertRaises(LaboratoryFileError) as refused:
            file.sudo()._add_version(content=content, source=EDITED_ONLINE, user=self.courier.user_id)
        self.assertEqual(refused.exception.code, PERMISSION_DENIED)
        devices = self.env[MODEL_LABORATORY_DEVICE].with_user(self.courier.user_id)
        _key, key_id = devices._new_key("PC-01")
        device = devices.sudo().create(
            {
                "user_id": self.courier.user_id.id,
                "client_uid": "6f1c3e0e-2a4b-4c55-9e1d-0b6f2a9c4e11",
                "name": "PC-01",
                "platform": "windows",
                "api_key_id": key_id,
            }
        )
        with self.assertRaises(LaboratoryFileError):
            file._check_can_add_version(self.courier.user_id, device)
        self.assertFalse(report.draft_ids.filtered(lambda draft: draft.docx_version_id.source == EDITED_ONLINE))

    def test_the_draft_is_read_with_permission_to_read_the_report_only(self):
        report, _candidate = self.prepared()
        report.draft_file_id.with_user(self.lab_head.user_id)._check_file_access("read")
        with self.assertRaises(LaboratoryFileError):
            report.draft_file_id.with_user(self.tester.user_id)._check_file_access("read")

    def test_printed_values_do_not_depend_on_who_asks(self):
        report = self.report()
        self.customer.partner_id.country_id = self.env.ref("base.vn")
        self.assertEqual(
            report.with_context(lang="vi_VN")._binding_values(), report.with_context(lang="en_US")._binding_values()
        )

    def test_changed_business_data_makes_the_candidate_out_of_date_and_the_job_prepares_a_new_one(self):
        report, candidate = self.prepared()
        self.customer.partner_id.name = "Công ty Nước Sạch Mới"
        self.assertFalse(candidate._is_current())
        report.invalidate_recordset(["candidate_current"])
        self.assertFalse(report.candidate_current)

        self.run_preparation()

        replacement = report._candidate()
        self.assertNotEqual(replacement, candidate)
        self.assertEqual(candidate.status, CANDIDATE_OBSOLETE)
        self.assertEqual(replacement.report_number, candidate.report_number)
        self.assertTrue(replacement._is_current())
        printed = report_docx.bindings(self.docx_of(replacement.docx_version_id))
        self.assertIn("Công ty Nước Sạch Mới", printed["customer_name"][0])

    def test_lab_head_prepares_the_pdf_again_from_the_current_records(self):
        report, candidate = self.prepared()
        self.customer.partner_id.name = "Công ty Nước Sạch Mới"

        self.as_person(report, self.lab_head).action_prepare_pdf()

        replacement = report._candidate()
        self.assertEqual(candidate.status, CANDIDATE_OBSOLETE)
        self.assertTrue(replacement._is_current())
        self.assertEqual(replacement.report_number, candidate.report_number)

    def test_lab_head_changes_the_template_and_gets_a_new_pdf_to_review(self):
        report, candidate = self.prepared()
        other = self.available_template(name="Water report, compact").version_ids
        wizard = self.as_person(self.env[MODEL_TEST_REPORT_TEMPLATE_CHANGE], self.lab_head).create(
            {"report_id": report.id, "template_version_id": other.id}
        )
        self.assertIn(other, wizard.available_version_ids)

        wizard.action_apply()

        replacement = report._candidate()
        self.assertEqual(candidate.status, CANDIDATE_OBSOLETE)
        self.assertEqual(report.template_version_id, other)
        self.assertEqual(report._latest_draft().template_version_id, other)
        self.assertEqual(replacement.template_version_id, other)
        self.assertEqual(replacement.report_number, candidate.report_number)
        self.assertTrue(replacement._is_current())
        # Keeping the same version changes nothing.
        with self.assertRaisesRegex(UserError, "already uses"):
            self.change_template(report, other, self.lab_head)
        self.assertEqual(report._candidate(), replacement)

    def test_the_lab_head_chooses_a_template_version_without_permission_to_read_templates(self):
        other = self.available_template(name="Water report, compact").version_ids
        versions = self.as_person(self.env[MODEL_REPORT_TEMPLATE_VERSION], self.lab_head)
        self.assertEqual(
            versions.name_search("", [("id", "=", other.id)]), [(other.id, "Water report, compact, version 1")]
        )

    def test_only_the_lab_head_prepares_the_pdf_again_or_changes_the_template(self):
        report, candidate = self.prepared()
        other = self.available_template(name="Water report, compact").version_ids
        with self.assertRaises(AccessError):
            self.as_person(report, self.courier).action_prepare_pdf()
        with self.assertRaises(AccessError):
            self.change_template(report, other, self.courier)
        self.assertEqual(report._candidate(), candidate)

    def test_lab_head_rejection_invalidates_the_candidate(self):
        report, candidate = self.prepared()
        self.as_person(report, self.lab_head).action_reject("Check lead again.", report.result_ids)
        self.assertEqual(candidate.status, CANDIDATE_OBSOLETE)

    def test_signed_report_keeps_its_pdf_and_prepares_no_other(self):
        report, _candidate = self.prepared()
        self.sign(report)
        self.assertEqual(report.status, "issued")
        self.assertFalse(report._candidate())
        with self.assertRaisesRegex(UserError, "signatures"):
            self.as_person(report, self.lab_head).action_prepare_pdf()
        self.run_preparation()
        self.assertEqual(len(report.candidate_ids), 1)

    def test_onlyoffice_outage_blocks_preparation_but_not_issued_downloads(self):
        report = self.report()
        self.health_check.return_value = False
        with self.assertRaisesRegex(UserError, "ONLYOFFICE is unavailable"):
            self.as_person(report, self.lab_head).action_prepare_pdf()
        # The job waits for ONLYOFFICE without counting a failed attempt.
        self.run_preparation()
        item = self.env[MODEL_JOB_ITEM].search([("document_model", "=", report._name), ("document_id", "=", report.id)])
        self.assertEqual((item.status, item.attempts), ("pending", 0))
        next_attempt_at = item.next_attempt_at
        self.assertGreater(assert_instance(next_attempt_at, datetime), assert_instance(fields.Datetime.now(), datetime))

        self.health_check.return_value = True
        self.conversion.side_effect = ConversionUnavailable("The editing service did not answer.")
        with self.assertRaisesRegex(UserError, "could not convert"):
            self.as_person(report, self.lab_head).action_prepare_pdf()
        self.assertFalse(report.candidate_ids)
        self.assertFalse(report.code)
        self.assertFalse(report.draft_ids)
        # A failed conversion is a failed attempt of the job, which tries again.
        item.next_attempt_at = fields.Datetime.now()
        self.run_preparation()
        self.assertEqual((item.status, item.attempts), ("pending", 1))
        self.assertFalse(report.candidate_ids)

        self.conversion.side_effect = None
        item.next_attempt_at = fields.Datetime.now()
        self.run_preparation()
        self.assertTrue(report._candidate())
        # A PDF prepared before the outage is signed and issued without ONLYOFFICE.
        self.health_check.return_value = False
        self.sign(report)
        self.assertEqual(report.status, "issued")
        download = self.as_person(report, self.courier).action_download()
        self.assertEqual(download["url"], f"/web/content/{report.attachment_id.id}?download=true")
