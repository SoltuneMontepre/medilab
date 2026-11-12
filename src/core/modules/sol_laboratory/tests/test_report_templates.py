from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .report_preparation_case import ReportPreparationCase
from odoo.addons.sol_laboratory.constants.laboratory_editing import OPEN
from odoo.addons.sol_laboratory.constants.laboratory_files import GENERATED, LOCKED, PERMISSION_DENIED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_EDITING_SESSION,
    MODEL_REPORT_TEMPLATE,
    MODEL_REPORT_TEMPLATE_VERSION,
)
from odoo.addons.sol_laboratory.constants.report_templates import ARCHIVED, AVAILABLE, DRAFT, REQUIRED_BINDINGS
from odoo.addons.sol_laboratory.services import report_docx
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError


@tagged("post_install", "-at_install")
class TestReportTemplates(ReportPreparationCase):
    def draft(self, template):
        return self.as_person(template._draft_version(), self.template_admin)

    def test_new_template_starts_with_a_draft_holding_every_binding(self):
        template = self.new_template("vi", "Phiếu kết quả")
        version = template.version_ids
        self.assertEqual(version.mapped("state"), [DRAFT])
        docx = template.file_id.current_version_id
        self.assertEqual(docx.source, GENERATED)
        self.assertEqual(set(report_docx.bindings(self.docx_of(docx))), set(REQUIRED_BINDINGS))

    def test_missing_binding_prevents_availability(self):
        template = self.new_template()
        version = self.draft(template)
        data = self.docx_of(template.file_id.current_version_id)
        without_samples = self.rewrite(data, b"medilab:samples", b"medilab:sample_list")
        self.save_docx(template.file_id, without_samples, self.template_admin.user_id)
        with self.assertRaisesRegex(UserError, "samples"):
            version.action_preview()
        self.assertEqual(version.state, DRAFT)
        with self.assertRaisesRegex(UserError, "samples"):
            version.action_make_available()
        self.assertEqual(version.state, DRAFT)

    def test_availability_needs_a_preview_of_the_last_save(self):
        template = self.new_template()
        version = self.draft(template)
        with self.assertRaisesRegex(UserError, "Preview"):
            version.action_make_available()
        version.action_preview()
        self.assertTrue(version.preview_attachment_id)
        laid_out = report_docx.fill(self.docx_of(version._docx()), {"customer_name": "[Khách hàng]"})
        self.save_docx(template.file_id, laid_out, self.template_admin.user_id)
        with self.assertRaisesRegex(UserError, "Preview"):
            version.action_make_available()

    def test_available_version_is_frozen_and_editing_creates_a_new_draft(self):
        version = self.template.version_ids
        self.assertEqual(version.state, AVAILABLE)
        frozen = version.docx_version_id
        self.assertEqual(frozen, self.template.file_id.current_version_id)
        with self.assertRaises(UserError):
            self.as_person(version, self.template_admin).action_edit()
        with self.assertRaises(LaboratoryFileError) as refused:
            self.save_docx(self.template.file_id, b"PK changed", self.template_admin.user_id)
        self.assertEqual(refused.exception.code, LOCKED)

        self.as_person(version, self.template_admin).action_new_draft()
        draft = self.template._draft_version()
        self.assertEqual(draft.number, 2)
        with self.assertRaisesRegex(UserError, "draft version"):
            self.as_person(version, self.template_admin).action_new_draft()
        laid_out = report_docx.fill(self.docx_of(frozen), {"customer_name": "[Khách hàng]"})
        self.save_docx(self.template.file_id, laid_out, self.template_admin.user_id)
        self.assertEqual(version.docx_version_id, frozen)
        self.assertNotEqual(draft._docx(), frozen)

    def test_reports_keep_their_version_when_it_is_archived(self):
        report = self.report()
        self.editor(report).action_edit_draft()
        version = self.template.version_ids
        self.assertEqual(report.template_version_id, version)
        self.as_person(version, self.template_admin).action_archive()
        self.assertEqual(version.state, ARCHIVED)
        self.assertFalse(version.active)
        self.assertEqual(report.template_version_id, version)
        self.assertEqual(report.draft_ids.template_version_id, version)
        # It is no longer offered, and the report can still be generated again from it.
        self.assertFalse(report._template_versions())
        self.editor(report).action_generate_draft()
        self.assertEqual(report._latest_draft().template_version_id, version)
        with self.assertRaises(UserError):
            self.as_person(version, self.template_admin).action_unarchive()

    def test_archived_version_cannot_be_chosen_for_a_new_draft(self):
        version = self.template.version_ids
        self.as_person(version, self.template_admin).action_archive()
        with self.assertRaisesRegex(UserError, "No report template"):
            self.editor().action_edit_draft()

    def test_person_without_template_permission_changes_nothing(self):
        template = self.new_template()
        version = template.version_ids
        for action in ("action_preview", "action_make_available", "action_edit"):
            with self.subTest(action=action), self.assertRaises(AccessError):
                getattr(self.as_person(version, self.courier), action)()
        with self.assertRaises(AccessError):
            self.as_person(self.env[MODEL_REPORT_TEMPLATE], self.courier).create({"name": "Mine", "language": "vi"})
        with self.assertRaises(UserError):
            self.as_person(version, self.template_admin).write({"state": AVAILABLE})
        with self.assertRaises(UserError):
            self.as_person(self.env[MODEL_REPORT_TEMPLATE_VERSION], self.template_admin).create(
                {"template_id": template.id, "number": 9}
            )
        with self.assertRaises(LaboratoryFileError) as refused:
            template.file_id.with_user(self.courier.user_id)._check_file_access("write")
        self.assertEqual(refused.exception.code, PERMISSION_DENIED)
        self.assertEqual(version.state, DRAFT)

    def test_open_editing_session_blocks_availability(self):
        template = self.new_template()
        version = self.draft(template)
        version.action_preview()
        sessions = self.env[MODEL_LABORATORY_EDITING_SESSION].with_user(self.template_admin.user_id)
        session = sessions._open_for(template.file_id.with_user(self.template_admin.user_id))
        self.assertEqual(session.status, OPEN)
        with self.assertRaisesRegex(UserError, "still editing"):
            version.action_make_available()
