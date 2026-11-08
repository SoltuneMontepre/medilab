from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .report_case import PDF
from .report_preparation_case import ReportPreparationCase
from odoo.addons.sol_laboratory.constants.laboratory_editing import ERROR, SESSION_CONFLICT
from odoo.addons.sol_laboratory.constants.laboratory_files import GENERATED, LOCKED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_CONTENT,
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_EDITING_SESSION,
    MODEL_TEST_REPORT_TEMPLATE_CHANGE,
)
from odoo.addons.sol_laboratory.constants.report_templates import CANDIDATE_OBSOLETE, CANDIDATE_REVIEW
from odoo.addons.sol_laboratory.services import report_docx
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.report_conversion import ConversionUnavailable


@tagged("post_install", "-at_install")
class TestReportPreparation(ReportPreparationCase):
    def prepared(self):
        report = self.report()
        self.editor(report).action_edit_draft()
        self.editor(report).action_prepare_pdf()
        return report, report._candidate()

    def open_session(self, report):
        sessions = self.env[MODEL_LABORATORY_EDITING_SESSION].with_user(self.courier.user_id)
        return sessions._open_for(report.draft_file_id.with_user(self.courier.user_id))

    def stored(self, data):
        return self.env[MODEL_LABORATORY_CONTENT]._store_bytes(data)

    def test_draft_is_generated_from_the_available_template_and_approved_results(self):
        report = self.report()
        action = self.editor(report).action_edit_draft()
        self.assertEqual(action["url"], f"/medilab/laboratory-files/{report.draft_file_id.id}/edit")
        draft = report.draft_ids
        self.assertEqual(draft.template_version_id, self.template.version_ids)
        self.assertEqual(draft.docx_version_id, report.draft_file_id.current_version_id)
        self.assertEqual(draft.docx_version_id.source, GENERATED)
        self.assertEqual(draft.result_ids, report.result_ids)
        printed = report_docx.bindings(self.docx_of(draft.docx_version_id))
        self.assertIn(self.request.code, printed["request_code"][0])
        self.assertIn(self.sample.code, printed["samples"][0])
        self.assertEqual(printed["report_number"], [""])

    def test_preparing_reserves_the_number_and_freezes_the_candidate(self):
        report, candidate = self.prepared()
        self.assertEqual(candidate.status, CANDIDATE_REVIEW)
        self.assertRegex(report.code, r"^PKQ\.")
        self.assertEqual(report.status, "draft")
        self.assertEqual(candidate.report_number, report.code)
        self.assertEqual(candidate.template_version_id, self.template.version_ids)
        self.assertEqual(candidate.docx_version_id, report.draft_file_id.current_version_id)
        self.assertEqual(bytes(candidate.attachment_id.raw), PDF)
        self.assertEqual(len(candidate.sha256), 64)
        self.assertEqual(candidate.result_ids, report.result_ids)
        self.assertTrue(candidate._is_current())
        printed = report_docx.bindings(self.docx_of(candidate.docx_version_id))
        self.assertEqual(printed["report_number"], [report.code])
        self.assertTrue(report.has_candidate and report.candidate_current)
        self.assertFalse(report.draft_editable)

    def test_reviewed_candidate_cannot_be_replaced_by_saves_or_late_callbacks(self):
        report = self.report()
        self.editor(report).action_edit_draft()
        session = self.open_session(report).sudo()
        session.last_activity_at = "2000-01-01 00:00:00"
        session._expire()
        self.editor(report).action_prepare_pdf()
        candidate = report._candidate()
        docx = candidate.docx_version_id
        # The expired session's save arrives after the PDF was prepared.
        late = session.sudo()._store_save(
            content=self.stored(b"PK late"), editor=self.courier.user_id, editors=self.courier.user_id
        )
        self.assertFalse(late)
        self.assertEqual(session.status, ERROR)
        self.assertEqual(report.draft_file_id.current_version_id, docx)
        self.assertEqual(candidate.docx_version_id, docx)
        self.assertTrue(candidate._is_current())
        with self.assertRaises(LaboratoryFileError) as refused:
            self.open_session(report)
        self.assertEqual(refused.exception.code, LOCKED)
        for action in ("action_prepare_pdf", "action_edit_draft"):
            with self.subTest(action=action), self.assertRaises(UserError):
                getattr(self.editor(report), action)()
        self.assertEqual(report._candidate(), candidate)

    def test_pending_save_blocks_preparation(self):
        report = self.report()
        self.editor(report).action_edit_draft()
        self.open_session(report)
        with self.assertRaisesRegex(UserError, "still editing"):
            self.editor(report).action_prepare_pdf()
        self.assertFalse(report.candidate_ids)
        self.assertFalse(report.code)

    def test_failed_and_conflicted_saves_block_preparation(self):
        report = self.report()
        self.editor(report).action_edit_draft()
        session = self.open_session(report).sudo()
        session._fail("The editing service could not save the document.")
        with self.assertRaisesRegex(UserError, "failed"):
            self.editor(report).action_prepare_pdf()

        session = self.open_session(report).sudo()
        self.save_docx(report.draft_file_id, b"PK newer", self.courier.user_id)
        conflict = session._store_save(
            content=self.stored(b"PK conflict"), editor=self.courier.user_id, editors=self.courier.user_id
        )
        self.assertEqual(session.status, SESSION_CONFLICT)
        self.assertEqual(conflict, session.committed_version_id)
        with self.assertRaisesRegex(UserError, "conflict"):
            self.editor(report).action_prepare_pdf()
        self.assertFalse(report.candidate_ids)

    def test_altered_or_removed_binding_blocks_preparation(self):
        report = self.report()
        self.editor(report).action_edit_draft()
        generated = self.docx_of(report.draft_file_id.current_version_id)
        file = report.draft_file_id
        self.save_docx(file, report_docx.fill(generated, {"customer_name": "Another customer"}), self.courier.user_id)
        with self.assertRaisesRegex(UserError, "customer_name"):
            self.editor(report).action_prepare_pdf()
        self.save_docx(file, self.rewrite(generated, b"medilab:samples", b"medilab:removed"), self.courier.user_id)
        with self.assertRaisesRegex(UserError, "samples"):
            self.editor(report).action_prepare_pdf()
        # Layout and explanatory text outside the bindings may change.
        note = b"<w:p><w:r><w:t>Ghi chu</w:t></w:r></w:p><w:sectPr"
        self.save_docx(file, self.rewrite(generated, b"<w:sectPr", note), self.courier.user_id)
        self.editor(report).action_prepare_pdf()
        self.assertTrue(report._candidate())

    def test_printed_values_do_not_depend_on_who_asks(self):
        report = self.report()
        self.customer.partner_id.country_id = self.env.ref("base.vn")
        self.assertEqual(
            report.with_context(lang="vi_VN")._binding_values(), report.with_context(lang="en_US")._binding_values()
        )

    def test_changed_business_data_makes_the_candidate_out_of_date(self):
        report, candidate = self.prepared()
        self.customer.partner_id.name = "Công ty Nước Sạch Mới"
        self.assertFalse(candidate._is_current())
        report.invalidate_recordset(["candidate_current"])
        self.assertFalse(report.candidate_current)
        self.editor(report).action_reopen_draft()
        self.assertEqual(candidate.status, CANDIDATE_OBSOLETE)
        with self.assertRaisesRegex(UserError, "customer_name"):
            self.editor(report).action_prepare_pdf()
        self.editor(report).action_generate_draft()
        self.editor(report).action_prepare_pdf()
        replacement = report._candidate()
        self.assertNotEqual(replacement, candidate)
        self.assertEqual(replacement.report_number, candidate.report_number)

    def test_template_switch_invalidates_the_unsigned_candidate(self):
        report, candidate = self.prepared()
        other = self.available_template(name="Water report, compact").version_ids
        wizard = self.as_person(self.env[MODEL_TEST_REPORT_TEMPLATE_CHANGE], self.courier).create(
            {"report_id": report.id, "template_version_id": other.id}
        )
        self.assertIn(other, wizard.available_version_ids)
        wizard.action_apply()
        self.assertEqual(candidate.status, CANDIDATE_OBSOLETE)
        self.assertEqual(report.template_version_id, other)
        self.assertEqual(report._latest_draft().template_version_id, other)
        self.assertFalse(report._candidate())

    def test_lab_head_rejection_invalidates_the_candidate(self):
        report, candidate = self.prepared()
        self.as_person(report, self.lab_head).action_reject("Check lead again.", report.result_ids)
        self.assertEqual(candidate.status, CANDIDATE_OBSOLETE)

    def test_signed_report_keeps_its_draft_locked(self):
        report, _candidate = self.prepared()
        self.sign(report)
        self.assertEqual(report.status, "issued")
        self.assertFalse(report._candidate())
        with self.assertRaises(LaboratoryFileError) as refused:
            report.draft_file_id.with_user(self.courier.user_id)._check_file_access("write")
        self.assertEqual(refused.exception.code, LOCKED)

    def test_onlyoffice_outage_blocks_preparation_but_not_issued_downloads(self):
        report = self.report()
        self.editor(report).action_edit_draft()
        self.health_check.return_value = False
        with self.assertRaisesRegex(UserError, "ONLYOFFICE is unavailable"):
            self.editor(report).action_prepare_pdf()
        self.health_check.return_value = True
        self.conversion.side_effect = ConversionUnavailable("The editing service did not answer.")
        with self.assertRaisesRegex(UserError, "could not convert"):
            self.editor(report).action_prepare_pdf()
        self.assertFalse(report.candidate_ids)
        self.assertFalse(report.code)

        self.conversion.side_effect = None
        self.editor(report).action_prepare_pdf()
        # A PDF prepared before the outage is signed and issued without ONLYOFFICE.
        self.health_check.return_value = False
        self.sign(report)
        self.assertEqual(report.status, "issued")
        download = self.as_person(report, self.courier).action_download()
        self.assertEqual(download["url"], f"/web/content/{report.attachment_id.id}?download=true")

    def test_person_without_report_edit_permission_cannot_edit_or_prepare(self):
        report = self.report()
        for action in ("action_edit_draft", "action_prepare_pdf", "action_generate_draft"):
            with self.subTest(action=action), self.assertRaises((AccessError, UserError)):
                getattr(self.as_person(report, self.lab_head), action)()
        self.editor(report).action_edit_draft()
        with self.assertRaises(LaboratoryFileError):
            report.draft_file_id.with_user(self.lab_head.user_id)._check_file_access("write")
        with self.assertRaises(LaboratoryFileError):
            report.draft_file_id.with_user(self.tester.user_id)._check_file_access("read")

    def test_computers_cannot_upload_to_report_drafts(self):
        report = self.report()
        self.editor(report).action_edit_draft()
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
            report.draft_file_id._check_can_add_version(self.courier.user_id, device)
