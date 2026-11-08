from typing import TYPE_CHECKING, cast

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import format_date

from odoo.addons.sol_laboratory.constants.laboratory_editing import ERROR, SESSION_CONFLICT
from odoo.addons.sol_laboratory.constants.laboratory_files import FILE_READ, GENERATED, LOCKED, PERMISSION_DENIED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DOCUMENT_LOCK,
    MODEL_LABORATORY_CONTENT,
    MODEL_LABORATORY_EDITING_SESSION,
    MODEL_LABORATORY_FILE,
    MODEL_REPORT_TEMPLATE,
    MODEL_REPORT_TEMPLATE_VERSION,
    MODEL_TEST_REPORT,
    MODEL_TEST_REPORT_CANDIDATE,
    MODEL_TEST_REPORT_DRAFT,
    MODEL_TEST_RESULT,
)
from odoo.addons.sol_laboratory.constants.report_templates import (
    ARCHIVED,
    AVAILABLE,
    CANDIDATE_REVIEW,
    ISSUE_BINDINGS,
    REQUIRED_BINDINGS,
)
from odoo.addons.sol_laboratory.constants.xml_ids import REPORT_DRAFTS_FOLDER
from odoo.addons.sol_laboratory.models.testing.test_report import ISSUED_STATUSES, PRINT_LANGS
from odoo.addons.sol_laboratory.services import laboratory_bucket, report_docx
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.report_docx import paragraph, table

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_report as TestReportBase
else:
    TestReportBase = object

# The details printed under a sample's heading, by their label keys.
SAMPLE_DETAILS = ("sample_type", "amount", "condition", "analysis_started")
# The bindings MediLab checks against business records before preparing the PDF.
BUSINESS_BINDINGS = tuple(name for name in REQUIRED_BINDINGS if name not in ISSUE_BINDINGS)


# Phiếu Kết Quả: its DOCX draft, generated from a template version and edited online, and the PDF prepared from it for
# the lab head's review.
class TestReport(models.Model, TestReportBase):
    _inherit = MODEL_TEST_REPORT
    _audit_children = ("draft_ids", "candidate_ids")

    if not TYPE_CHECKING:
        # The template version the report's draft is generated from.
        template_version_id = fields.Many2one(
            MODEL_REPORT_TEMPLATE_VERSION, string="Template Version", readonly=True, copy=False, ondelete="restrict"
        )
        # The working DOCX of the report; each generation and save is one of its versions.
        draft_file_id = fields.Many2one(
            MODEL_LABORATORY_FILE, string="DOCX Draft", readonly=True, copy=False, ondelete="restrict"
        )
        # Every generation of the draft, the latest first.
        draft_ids = fields.One2many(MODEL_TEST_REPORT_DRAFT, "report_id", string="Generated Drafts")
        # Every PDF prepared for review, the latest first.
        candidate_ids = fields.One2many(MODEL_TEST_REPORT_CANDIDATE, "report_id", string="Prepared PDFs")
        # The prepared PDF waiting for the lab head's review and signature; the sign button names it, so a signer never
        # signs a PDF prepared after the one they reviewed.
        candidate_id = fields.Many2one(MODEL_TEST_REPORT_CANDIDATE, string="PDF to Sign", compute="_compute_candidate")
        # True while a prepared PDF waits for the lab head's review.
        has_candidate = fields.Boolean(string="PDF Waiting for Review", compute="_compute_candidate")
        # True while that PDF still matches its template version, its draft's last save and the business records.
        candidate_current = fields.Boolean(compute="_compute_candidate")
        # True while the draft can be generated, edited and prepared: the report is unsigned and no PDF waits.
        draft_editable = fields.Boolean(compute="_compute_candidate")

    _draft_file_unique = models.Constraint("UNIQUE(draft_file_id)", "A DOCX draft belongs to one test report.")

    @api.depends("candidate_ids.status", "status", "draft_file_id.current_version_id")
    def _compute_candidate(self):
        for report in self:
            candidate = report.sudo()._candidate()
            report.candidate_id = candidate
            report.has_candidate = bool(candidate)
            report.candidate_current = bool(candidate) and candidate._is_current()
            report.draft_editable = bool(report.id) and report.sudo()._docx_writable_error() is None

    def _candidate(self):
        """The prepared PDF waiting for review and signature; none once the report is issued."""
        self.ensure_one()
        report = self.sudo()
        if report.status in ISSUED_STATUSES:
            return report.candidate_ids.browse()
        return report.candidate_ids.filtered(lambda candidate: candidate.status == CANDIDATE_REVIEW)[:1]

    def _docx_writable_error(self):
        """Why the draft cannot change now, or None when it can."""
        report = self.sudo()
        if report.status != "draft" or report._approval_has_standing():
            return self.env._("The report has signatures; its draft stays as it was signed.")
        if report._candidate():
            return self.env._("The report's PDF waits for review; reopen the draft to change it.")
        return None

    def _check_docx_access(self, access):
        """Refuse the user reading the report's DOCX without permission to read the report and its request, and writing
        it without permission to edit the report or while it is signed or its PDF waits for review."""
        self.ensure_one()
        try:
            self._check_permission("read" if access == FILE_READ else "edit")
            self.check_access("read")
            self.request_id.check_access("read")
        except AccessError:
            raise LaboratoryFileError(
                PERMISSION_DENIED, self.env._("You do not have permission to open this report's draft.")
            ) from None
        if access != FILE_READ:
            self._check_docx_writable()

    def _check_docx_writable(self):
        error = self._docx_writable_error()
        if error:
            raise LaboratoryFileError(LOCKED, error)

    def _check_report_editor(self):
        """Refuse a user who may not edit the report, or whose report's draft cannot change now."""
        self.ensure_one()
        try:
            self._check_docx_access("write")
        except LaboratoryFileError as error:
            raise UserError(error.args[0]) from None

    def _template_versions(self):
        """The available template versions the report may use: those of its language."""
        self.ensure_one()
        return (
            self.env[MODEL_REPORT_TEMPLATE_VERSION]
            .sudo()
            .search([("state", "=", AVAILABLE), ("language", "=", self.sudo().language)])
        )

    def _default_template_version(self):
        """The latest available version of the first template of the report's language that has one."""
        self.ensure_one()
        templates = self.env[MODEL_REPORT_TEMPLATE].sudo().search([("language", "=", self.sudo().language)])
        for template in templates:
            versions = template.version_ids.filtered(lambda version: version.state == AVAILABLE)
            if versions:
                return versions.sorted("number")[-1]
        return self.env[MODEL_REPORT_TEMPLATE_VERSION]

    def action_edit_draft(self):
        """Open the report's DOCX draft in the online editor, generating it first when it has none."""
        self.ensure_one()
        self._check_report_editor()
        if not self._latest_draft():
            self._generate_draft()
        return {
            "type": "ir.actions.act_url",
            "url": f"/medilab/laboratory-files/{self.draft_file_id.id}/edit",
            "target": "new",
        }

    def action_generate_draft(self):
        """Generate the draft again from the template version and the business records, replacing the editors'
        changes; its waiting PDF, if any, becomes obsolete."""
        self.ensure_one()
        self._check_permission("edit")
        self._candidate()._invalidate(self.env._("The draft was generated again."))
        self._check_report_editor()
        self._generate_draft()

    def action_reopen_draft(self):
        """Make the PDF waiting for review obsolete, so the draft can be edited and prepared again."""
        self.ensure_one()
        self._check_permission("edit")
        candidate = self._candidate()
        if not candidate:
            raise UserError(self.env._("The report has no PDF waiting for review."))
        candidate._invalidate(self.env._("The draft was reopened."))
        self._check_report_editor()

    def _change_template(self, version):
        """Generate the draft again from another available template version of the report's language; its waiting PDF
        becomes obsolete."""
        self.ensure_one()
        self._check_permission("edit")
        if version == self.sudo().template_version_id:
            raise UserError(self.env._("The report already uses this template version."))
        self._candidate()._invalidate(self.env._("Another template version was chosen."))
        self._check_report_editor()
        self._generate_draft(version)

    def _generate_draft(self, version=None):
        """Fill the template version with the report's business data, leaving the issue details empty, and store it as
        the draft's new version. A version other than the report's own must be available in its language."""
        self.ensure_one()
        report = self.sudo()
        current = report.template_version_id
        version = (version or current or report._default_template_version()).sudo()
        if not version:
            raise UserError(self.env._("No report template is available in the report's language yet."))
        if version.language != report.language or (
            version.state != AVAILABLE and not (version == current and version.state == ARCHIVED)
        ):
            raise UserError(self.env._("Choose an available template version in the report's language."))
        file = report._draft_file()
        if file._open_editing_sessions():
            raise UserError(self.env._("Someone is editing the draft; wait until the editor has saved it."))
        values = {**report._binding_values(), **dict.fromkeys(ISSUE_BINDINGS, "")}
        docx = version.docx_version_id
        try:
            filled = report_docx.fill(docx.content_id._read_bytes(), values)
            content = self.env[MODEL_LABORATORY_CONTENT]._store_bytes(filled)
        except laboratory_bucket.BucketUnavailable:
            raise UserError(
                self.env._("The laboratory files storage is unavailable; generate the draft later.")
            ) from None
        report.template_version_id = version
        generated = file._add_version(content=content, source=GENERATED, user=self.env.user)
        report.env[MODEL_TEST_REPORT_DRAFT].create(
            {
                "report_id": report.id,
                "template_version_id": version.id,
                "docx_version_id": generated.id,
                "result_ids": report.result_ids.ids,
                "snapshot": values,
            }
        )
        return generated

    def _latest_draft(self):
        """The report's last generated draft."""
        self.ensure_one()
        return self.env[MODEL_TEST_REPORT_DRAFT].sudo().search([("report_id", "=", self.id)], limit=1)

    def _draft_file(self):
        report = self.sudo()
        if not report.draft_file_id:
            folder = self.env.ref(REPORT_DRAFTS_FOLDER)
            path = f"{report.id}/{report.request_id.code}-v{report.version}.docx"
            report.draft_file_id = report.env[MODEL_LABORATORY_FILE]._get_or_create(folder, path)
        return report.draft_file_id

    def action_prepare_pdf(self):
        """Freeze the draft's last save as the PDF the lab head reviews and signs, with the reserved report number."""
        self.ensure_one()
        self._check_report_editor()
        # A second click is refused while the first preparation converts the document.
        with self.env[MODEL_DOCUMENT_LOCK]._operation(self):
            self._prepare_candidate()

    def _prepare_candidate(self):
        report = self.sudo()
        try:
            self.env[MODEL_LABORATORY_EDITING_SESSION]._check_editing_available()
        except LaboratoryFileError as error:
            raise UserError(
                self.env._("ONLYOFFICE is unavailable, so no new PDF can be prepared: %s", error.args[0])
            ) from None
        if not report._latest_draft():
            report._generate_draft()
        file = report.draft_file_id
        # Saves of the draft wait for this preparation, then see the PDF waiting for review and are refused.
        file._lock_for_new_version()
        report._check_saves_finished(file)
        if report._latest_draft().template_version_id != report.template_version_id:
            raise UserError(self.env._("The draft was not generated from the report's template; generate it again."))
        current = file.current_version_id
        business = report._binding_values()
        # The module ships the report sequence, so a number always comes back.
        number = report.code or cast("str", self.env["ir.sequence"].next_by_code(MODEL_TEST_REPORT))
        day = report._laboratory_day(fields.Datetime.now())
        try:
            docx = current.content_id._read_bytes()
            report._check_draft_matches(docx, business)
            final = report_docx.fill(
                docx, {"report_number": number, "report_date": format_date(report._print_env(), day)}
            )
            content = self.env[MODEL_LABORATORY_CONTENT]._store_bytes(final)
        except laboratory_bucket.BucketUnavailable:
            raise UserError(self.env._("The laboratory files storage is unavailable; prepare the PDF later.")) from None
        # The number is reserved for this version of the report; issuing it makes it official.
        report.code = number
        final_version = file._add_version(content=content, source=GENERATED, user=self.env.user, base_version=current)
        candidates = self.env[MODEL_TEST_REPORT_CANDIDATE]
        pdf = candidates._convert(final_version.content_id, f"{number}.docx")
        return candidates._store(report, final_version, pdf, business, number, day)

    def _check_saves_finished(self, file):
        """Refuse preparing while someone edits the draft, its last save failed or it saved a conflict."""
        session = self.env[MODEL_LABORATORY_EDITING_SESSION].sudo().search([("file_id", "=", file.id)], limit=1)
        current = file.current_version_id
        if file._open_editing_sessions():
            raise UserError(self.env._("Someone is still editing the draft; close the editor and wait for its save."))
        if session.status == ERROR and session.base_version_id == current:
            raise UserError(self.env._("The last save of the draft failed; open the draft again and save it."))
        if session.status == SESSION_CONFLICT and session.committed_version_id.number > current.number:
            raise UserError(
                self.env._(
                    "The last save of the draft conflicts with a newer version; open the draft and save it again."
                )
            )

    def _check_draft_matches(self, docx, values):
        """Refuse a saved draft whose business bindings were removed or no longer print the business records."""
        try:
            saved = report_docx.bindings(docx)
            expected = report_docx.bindings(report_docx.fill(docx, values))
        except report_docx.ReportDocumentInvalid:
            raise UserError(self.env._("The saved draft is not a DOCX document that can be read.")) from None
        missing = [name for name in REQUIRED_BINDINGS if name not in saved]
        changed = [name for name in BUSINESS_BINDINGS if name in saved and saved[name] != expected[name]]
        if missing:
            raise UserError(self.env._("The draft misses bindings, generate it again: %s", ", ".join(missing)))
        if changed:
            raise UserError(
                self.env._(
                    "The draft no longer prints the business records for %s; correct the records through their "
                    "workflow and generate the draft again.",
                    ", ".join(changed),
                )
            )

    def action_open_candidate(self):
        """Show the PDF waiting for review."""
        self.ensure_one()
        candidate = self._candidate()
        if not candidate:
            raise UserError(self.env._("The report has no PDF waiting for review."))
        return candidate.with_env(self.env).action_open()

    def action_reject(self, reason, results=None):
        result = super().action_reject(reason, results)
        self._candidate()._invalidate(self.env._("The lab head rejected the report."))
        return result

    def _binding_values(self):
        """The business values the report's bindings print, by binding name, in the report's language whoever asks."""
        self.ensure_one()
        report = self.sudo().with_context(lang=self.sudo()._print_langs()[0])
        header = report._print_header()
        labels = report._print_labels()
        return {
            "request_code": header["request"],
            "customer_name": header["customer"] or "",
            "customer_address": header["address"],
            "received_dates": header["received"],
            "samples": report._sample_blocks(report._binding_samples(), labels),
            # The report's own signatures come after its PDF is prepared, so they never print in it.
            "approvers": [
                paragraph(f"{signer['name']}, {signer['level']}")
                for signer in report._print_signers(report_signers=False)
            ],
        }

    def _binding_samples(self):
        """Each sample the report covers, with its details, conclusion and one row per reported result."""
        report = self.sudo()
        env = report._print_env()
        results = report.result_ids.sorted("id")
        marks = report._print_marks(results.parameter_method_id)
        samples = []
        for sample, own in sorted(results.grouped("sample_id").items(), key=lambda item: item[0].code):
            started = sorted(filter(None, own.mapped("started_at")))
            compared = any(own.mapped("comparison_requested"))
            samples.append(
                {
                    "name": sample.customer_sample_name or "",
                    "code": sample.code or "",
                    "sample_type": report._in_langs(
                        lambda lang_env, sample=sample: sample.with_env(lang_env).sample_type_id.name
                    ),
                    "amount": sample.received_quantity or "",
                    "condition": report._in_langs(
                        lambda lang_env, sample=sample: dict(
                            sample._fields["condition"]._description_selection(lang_env)
                        ).get(sample.condition or "", "")
                    )
                    if sample.condition
                    else "",
                    "analysis_started": format_date(env, report._laboratory_day(started[0])) if started else "",
                    "conclusion": report._print_conclusion(own),
                    "rows": [
                        report._print_row(result, marks.get(result.parameter_method_id, ""), env, compared)
                        for result in own
                    ],
                }
            )
        return samples

    @api.model
    def _sample_blocks(self, samples, labels):
        """The paragraphs and tables of the samples binding: each sample's heading, details, conclusion and results."""
        blocks = []
        for sample in samples:
            blocks.append(
                paragraph(f"{labels['sample']}: {sample['name']} ({labels['lab_code']}: {sample['code']})", bold=True)
            )
            details = [f"{labels[key]}: {sample[key]}" for key in SAMPLE_DETAILS if sample.get(key)]
            if details:
                blocks.append(paragraph("; ".join(details)))
            if sample["conclusion"]:
                blocks.append(paragraph(f"{labels['conclusion']}: {sample['conclusion']}"))
            columns = list(sample["rows"][0])
            blocks.append(
                table(
                    [labels[column] for column in columns],
                    [[row[column] for column in columns] for row in sample["rows"]],
                )
            )
        return blocks

    @api.model
    def _example_binding_values(self, language):
        """Example values a template version's preview prints, in the template's languages."""
        langs = PRINT_LANGS[language]
        labels = self._labels_in(langs)
        example = self.with_context(lang=langs[0]).env
        today = fields.Date.context_today(self)
        passed = dict(self.env[MODEL_TEST_RESULT]._fields["conclusion"]._description_selection(example))["pass"]
        sample = {
            "name": example._("Bottled drinking water 500 mL, lot 1001"),
            "code": "PTN.2026.0001",
            "sample_type": example._("Bottled drinking water"),
            "amount": "2 × 500 mL",
            "condition": example._("Good"),
            "analysis_started": format_date(example, today),
            "conclusion": example._("Meets %s for the compared parameters", "QCVN 6-1:2010/BYT"),
            "rows": [
                {
                    "parameter": "Lead (Pb)",
                    "result": "0,004",
                    "unit": "mg/L",
                    "limit": "≤ 0,01",
                    "conclusion": passed,
                    "method": "SMEWW 3113B",
                },
                {
                    "parameter": "pH",
                    "result": "7,2",
                    "unit": "",
                    "limit": "6,5 – 8,5",
                    "conclusion": passed,
                    "method": "TCVN 6492:2011",
                },
            ],
        }
        return {
            "report_number": "PKQ.2026.0001",
            "report_date": format_date(example, today),
            "request_code": "YC.2026.0001",
            "customer_name": example._("Example Customer Co., Ltd."),
            "customer_address": example._("12 Nguyen Hue, District 1, Ho Chi Minh City"),
            "received_dates": format_date(example, today),
            "samples": self._sample_blocks([sample], labels),
            "approvers": [paragraph(example._("Example approver, Head of Department"))],
        }
