import hashlib
import json
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_IR_ATTACHMENT,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_PERMISSION_MIXIN,
    MODEL_REPORT_TEMPLATE_VERSION,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_TEST_REPORT,
    MODEL_TEST_REPORT_CANDIDATE,
    MODEL_TEST_RESULT,
)
from odoo.addons.sol_laboratory.constants.report_templates import (
    CANDIDATE_ISSUED,
    CANDIDATE_MIGRATED,
    CANDIDATE_OBSOLETE,
    CANDIDATE_PREPARED,
    CANDIDATE_REVIEW,
)
from odoo.addons.sol_laboratory.services import laboratory_bucket
from odoo.addons.sol_laboratory.services.report_conversion import ConversionUnavailable, convert_to_pdf

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_report_candidate as TestReportCandidateBase
else:
    TestReportCandidateBase = object

# What changes on a candidate once it is stored: its status, and why and when it became obsolete.
STATUS_FIELDS = frozenset({"status", "invalidated_reason", "invalidated_at"})


# Bản PDF Chờ Duyệt: the PDF prepared from one saved DOCX of a report, frozen for the lab head's review and signature.
class TestReportCandidate(models.Model, TestReportCandidateBase):
    _name = MODEL_TEST_REPORT_CANDIDATE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Prepared Test Report PDF"
    _order = "id desc"
    # Preparing a report's PDF makes them; only their status changes.
    _permission_actions = ("read",)

    if not TYPE_CHECKING:
        # The report the PDF is of.
        report_id = fields.Many2one(
            MODEL_TEST_REPORT, string="Report", required=True, readonly=True, ondelete="restrict", index=True
        )
        # prepared from a DOCX draft, or migrated from a report issued before report templates.
        origin = fields.Selection(
            [(CANDIDATE_PREPARED, "Prepared"), (CANDIDATE_MIGRATED, "Migrated")],
            required=True,
            default=CANDIDATE_PREPARED,
            readonly=True,
        )
        # review while it waits for the lab head, obsolete once replaced or out of date, issued once issued.
        status = fields.Selection(
            [(CANDIDATE_REVIEW, "Waiting for Review"), (CANDIDATE_OBSOLETE, "Obsolete"), (CANDIDATE_ISSUED, "Issued")],
            required=True,
            default=CANDIDATE_REVIEW,
            readonly=True,
            index=True,
        )
        # The exact template version the PDF was prepared with; empty for a migrated report.
        template_version_id = fields.Many2one(
            MODEL_REPORT_TEMPLATE_VERSION, string="Template Version", readonly=True, ondelete="restrict"
        )
        # The saved DOCX converted, holding the printed issue details; empty for a migrated report.
        docx_version_id = fields.Many2one(
            MODEL_LABORATORY_FILE_VERSION, string="DOCX", readonly=True, ondelete="restrict"
        )
        # The PDF.
        attachment_id = fields.Many2one(MODEL_IR_ATTACHMENT, string="PDF", readonly=True, ondelete="restrict")
        # SHA-256 of the PDF, in hexadecimal, which the signature of its review records.
        sha256 = fields.Char(string="SHA-256", required=True, readonly=True)
        # The report number printed, reserved for the report version when the PDF was prepared.
        report_number = fields.Char(readonly=True)
        # The report date printed: the day the PDF was prepared, in the laboratory's time zone.
        report_date = fields.Date(readonly=True)
        # The approved result versions the PDF prints.
        result_ids = fields.Many2many(
            MODEL_TEST_RESULT,
            "medilab_test_report_candidate_result_rel",
            "candidate_id",
            "result_id",
            string="Results",
            readonly=True,
        )
        # The business values the PDF prints, by binding name, as they were when it was prepared.
        snapshot = fields.Json(readonly=True)
        # Why the candidate is obsolete, such as the draft being reopened.
        invalidated_reason = fields.Char(readonly=True)
        # When the candidate became obsolete.
        invalidated_at = fields.Datetime(readonly=True)

    _one_in_review = models.UniqueIndex(
        f"(report_id) WHERE status = '{CANDIDATE_REVIEW}'", "The report already has a PDF waiting for review."
    )
    _prepared_sources = models.Constraint(
        f"CHECK(origin = '{CANDIDATE_MIGRATED}' OR (template_version_id IS NOT NULL AND docx_version_id IS NOT NULL))",
        "A prepared PDF keeps the template version and the DOCX it was prepared from.",
    )
    _sha256_format = models.Constraint("CHECK(sha256 ~ '^[0-9a-f]{64}$')", "A SHA-256 is 64 hexadecimal digits.")

    @api.depends("report_id.display_name", "status")
    def _compute_display_name(self):
        statuses = dict(self._fields["status"]._description_selection(self.env))
        for candidate in self:
            candidate.display_name = f"{candidate.report_id.display_name}, {statuses.get(candidate.status or '', '')}"

    def write(self, vals):
        if set(vals) - STATUS_FIELDS:
            raise UserError(self.env._("A prepared PDF never changes; prepare the report's PDF again instead."))
        return super().write(vals)

    def _files_locked(self):
        return True

    @api.model
    def _convert(self, content, title):
        """The PDF of the stored DOCX content, which ONLYOFFICE converts from a presigned address of its object. Refuses
        while ONLYOFFICE or the bucket is unavailable, so nothing older is used instead."""
        content = content.sudo()
        try:
            seconds = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("laboratory_file_url_minutes") * 60
            url = laboratory_bucket.read_address(content.object_key, seconds, title)
            return convert_to_pdf(url, content.sha256, title)
        except (ConversionUnavailable, laboratory_bucket.BucketUnavailable):
            raise UserError(
                self.env._("ONLYOFFICE could not convert the document to PDF right now; prepare it again later.")
            ) from None

    @api.model
    def _store(self, report, docx_version, pdf, snapshot, report_number, report_date):
        """Store a PDF prepared from the saved DOCX for review."""
        attachment = (
            self.env[MODEL_IR_ATTACHMENT]
            .sudo()
            .create(
                {"name": f"{report_number}.pdf", "raw": pdf, "mimetype": "application/pdf", "res_model": self._name}
            )
        )
        candidate = self.sudo().create(
            {
                "report_id": report.id,
                "template_version_id": report.sudo().template_version_id.id,
                "docx_version_id": docx_version.id,
                "attachment_id": attachment.id,
                "sha256": hashlib.sha256(pdf).hexdigest(),
                "report_number": report_number,
                "report_date": report_date,
                "result_ids": report.sudo().result_ids.ids,
                "snapshot": _jsonable(snapshot),
            }
        )
        attachment.res_id = candidate.id
        return candidate

    def _invalidate(self, reason):
        """Make the candidates waiting for review obsolete, so they can no longer be signed."""
        waiting = self.sudo().filtered(lambda candidate: candidate.status == CANDIDATE_REVIEW)
        waiting.write(
            {"status": CANDIDATE_OBSOLETE, "invalidated_reason": reason, "invalidated_at": fields.Datetime.now()}
        )

    def _is_current(self):
        """True while the candidate still waits for review and matches its report: the same template version, its draft's
        last save, the same results and the same printed business values. The signature of the report checks it."""
        self.ensure_one()
        candidate = self.sudo()
        report = candidate.report_id
        return bool(
            candidate.status == CANDIDATE_REVIEW
            and report.template_version_id == candidate.template_version_id
            and report.draft_file_id.current_version_id == candidate.docx_version_id
            and report.result_ids == candidate.result_ids
            and _jsonable(report._binding_values()) == candidate.snapshot
        )

    def action_open(self):
        self.ensure_one()
        return {"type": "ir.actions.act_url", "url": f"/web/content/{self.attachment_id.id}", "target": "new"}


def _jsonable(values):
    # Tuples become lists, as they do once stored, so stored and fresh values compare equal.
    return json.loads(json.dumps(values))
