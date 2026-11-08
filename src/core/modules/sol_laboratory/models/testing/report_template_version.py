from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.laboratory_files import RESTORED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_IR_ATTACHMENT,
    MODEL_LABORATORY_CONTENT,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_LOCK_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_REPORT_TEMPLATE,
    MODEL_REPORT_TEMPLATE_VERSION,
    MODEL_TEST_REPORT,
    MODEL_TEST_REPORT_CANDIDATE,
)
from odoo.addons.sol_laboratory.constants.report_templates import (
    ARCHIVED,
    AVAILABLE,
    BLOCK_BINDINGS,
    DRAFT,
    REQUIRED_BINDINGS,
)
from odoo.addons.sol_laboratory.services import laboratory_bucket, report_docx

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_report_template_version as ReportTemplateVersionBase
else:
    ReportTemplateVersionBase = object


# Phiên Bản Mẫu Phiếu Kết Quả
class ReportTemplateVersion(models.Model, ReportTemplateVersionBase):
    _name = MODEL_REPORT_TEMPLATE_VERSION
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Report Template Version"
    _order = "template_id, number desc"
    # Versions change only through their actions: editing and previewing a draft, making it available and archiving it.
    _permission_actions = ("read", "create", "edit", "archive")

    if not TYPE_CHECKING:
        # The template the version is of.
        template_id = fields.Many2one(
            MODEL_REPORT_TEMPLATE, string="Template", required=True, readonly=True, ondelete="restrict", index=True
        )
        # Language of the template, which reports choose versions by.
        language = fields.Selection(related="template_id.language", store=True)
        # Number of the version within its template, 1 for the first.
        number = fields.Integer(required=True, readonly=True)
        # draft while edited, available for new reports, archived once no new report may use it.
        state = fields.Selection(
            [(DRAFT, "Draft"), (AVAILABLE, "Available"), (ARCHIVED, "Archived")],
            string="Status",
            required=True,
            default=DRAFT,
            readonly=True,
        )
        # False once archived, so lists show the versions in use.
        active = fields.Boolean(default=True, readonly=True)
        # The saved DOCX the version froze when it became available; empty while draft.
        docx_version_id = fields.Many2one(
            MODEL_LABORATORY_FILE_VERSION, string="DOCX", readonly=True, copy=False, ondelete="restrict"
        )
        # PDF of the version filled with example data, made from preview_docx_version_id.
        preview_attachment_id = fields.Many2one(
            MODEL_IR_ATTACHMENT, string="Preview", readonly=True, copy=False, ondelete="restrict"
        )
        # The saved DOCX the preview was made from; making the version available needs a preview of its last save.
        preview_docx_version_id = fields.Many2one(
            MODEL_LABORATORY_FILE_VERSION, string="Previewed DOCX", readonly=True, copy=False, ondelete="restrict"
        )
        # When the version became available.
        made_available_at = fields.Datetime(readonly=True, copy=False)

    _template_number_unique = models.Constraint(
        "UNIQUE(template_id, number)", "A template has one version of each number."
    )
    _one_draft = models.UniqueIndex(
        f"(template_id) WHERE state = '{DRAFT}'", "The template already has a draft version; edit that one."
    )
    _frozen_docx = models.Constraint(
        f"CHECK(state = '{DRAFT}' OR docx_version_id IS NOT NULL)",
        "An available or archived template version keeps the DOCX it was made available with.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise UserError(self.env._("A template version is created from its template or from an available version."))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            raise UserError(self.env._("A template version changes only through its actions."))
        return super().write(vals)

    @api.depends("template_id.name", "number")
    def _compute_display_name(self):
        for version in self:
            version.display_name = self.env._(
                "%(template)s, version %(number)s", template=version.template_id.name or "", number=version.number
            )

    def _docx(self):
        """The DOCX of the version: the one it froze, or the last save of its template while it is a draft."""
        self.ensure_one()
        version = self.sudo()
        return version.docx_version_id or version.template_id.file_id.current_version_id

    def _check_draft(self):
        if any(version.state != DRAFT for version in self):
            raise UserError(
                self.env._("An available template version never changes; create a new draft version to edit it.")
            )

    def action_edit(self):
        """Open the draft's DOCX in the online editor."""
        self.ensure_one()
        self._check_permission("edit")
        self._check_draft()
        return {
            "type": "ir.actions.act_url",
            "url": f"/medilab/laboratory-files/{self.sudo().template_id.file_id.id}/edit",
            "target": "new",
        }

    def action_preview(self):
        """Fill the draft's last save with example data, convert it to PDF and show it."""
        self.ensure_one()
        self._check_permission("edit")
        self._check_draft()
        version = self.sudo()
        docx = version._docx()
        name = self.env._("Preview of %s", version.display_name)
        try:
            data = docx.content_id._read_bytes()
            self._check_bindings(data)
            example = self.env[MODEL_TEST_REPORT]._example_binding_values(version.template_id.language)
            content = self.env[MODEL_LABORATORY_CONTENT]._store_bytes(report_docx.fill(data, example))
        except laboratory_bucket.BucketUnavailable:
            raise UserError(
                self.env._("The laboratory files storage is unavailable; preview the version later.")
            ) from None
        pdf = self.env[MODEL_TEST_REPORT_CANDIDATE]._convert(content, f"{name}.docx")
        attachment = (
            self.env[MODEL_IR_ATTACHMENT]
            .sudo()
            .create(
                {
                    "name": f"{name}.pdf",
                    "raw": pdf,
                    "mimetype": "application/pdf",
                    "res_model": self._name,
                    "res_id": version.id,
                }
            )
        )
        version.write({"preview_attachment_id": attachment.id, "preview_docx_version_id": docx.id})
        return self.action_open_preview()

    def action_open_preview(self):
        self.ensure_one()
        attachment = self.sudo().preview_attachment_id
        if not attachment:
            raise UserError(self.env._("This version has no preview yet."))
        return {"type": "ir.actions.act_url", "url": f"/web/content/{attachment.id}", "target": "new"}

    def action_make_available(self):
        """Freeze the draft's last save as the version new reports of its language use, once its bindings are complete,
        its editors have finished saving and it was previewed."""
        self.ensure_one()
        self._check_permission("edit")
        self._check_draft()
        version = self.sudo()
        docx = version._docx()
        if version.template_id.file_id._open_editing_sessions():
            raise UserError(self.env._("Someone is still editing this template; wait until the editor has saved it."))
        try:
            self._check_bindings(docx.content_id._read_bytes())
        except laboratory_bucket.BucketUnavailable:
            raise UserError(self.env._("The laboratory files storage is unavailable; try again later.")) from None
        if version.preview_docx_version_id != docx:
            raise UserError(self.env._("Preview the last save of this version before making it available."))
        version.write({"state": AVAILABLE, "docx_version_id": docx.id, "made_available_at": fields.Datetime.now()})

    def action_archive(self):
        """Stop new reports from using the versions; reports already using them keep them."""
        self._check_permission("archive")
        if any(version.state != AVAILABLE for version in self):
            raise UserError(self.env._("Only an available template version is archived."))
        return self.sudo().write({"state": ARCHIVED, "active": False})

    def action_unarchive(self):
        raise UserError(self.env._("An archived template version stays archived; create a new version instead."))

    def action_new_draft(self):
        """Start a new draft version from this available version's DOCX."""
        self.ensure_one()
        self._check_permission("create")
        version = self.sudo()
        template = version.template_id
        if version.state != AVAILABLE:
            raise UserError(self.env._("A new version starts from an available version."))
        if template._draft_version():
            raise UserError(self.env._("The template already has a draft version; edit that one."))
        if template.file_id._open_editing_sessions():
            raise UserError(self.env._("Someone is still editing this template; wait until the editor has saved it."))
        # The unique index of drafts is checked against the states written so far.
        self.flush_model(["state"])
        draft = version.create({"template_id": template.id, "number": max(template.version_ids.mapped("number")) + 1})
        if template.file_id.current_version_id != version.docx_version_id:
            template.file_id._add_version(source=RESTORED, user=self.env.user, restored_from=version.docx_version_id)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": draft.id,
            "view_mode": "form",
        }

    def _check_bindings(self, docx):
        """Refuse a DOCX that misses a required binding, names one MediLab does not fill, or places a block binding
        inside a line of text."""
        try:
            found = report_docx.bindings(docx)
            blocks = report_docx.block_bindings(docx)
        except report_docx.ReportDocumentInvalid:
            raise UserError(self.env._("The template is not a DOCX document that can be read.")) from None
        missing = [name for name in REQUIRED_BINDINGS if name not in found]
        unknown = sorted(set(found) - set(REQUIRED_BINDINGS))
        inline = [name for name in BLOCK_BINDINGS if name in found and name not in blocks]
        if missing:
            raise UserError(self.env._("The template misses required bindings: %s", ", ".join(missing)))
        if unknown:
            raise UserError(self.env._("The template has bindings MediLab does not fill: %s", ", ".join(unknown)))
        if inline:
            raise UserError(
                self.env._("These bindings need paragraphs of their own, not a place in a line: %s", ", ".join(inline))
            )
