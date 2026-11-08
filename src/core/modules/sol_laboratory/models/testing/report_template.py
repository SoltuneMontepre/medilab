import re
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.laboratory_files import FILE_READ, GENERATED, LOCKED, PERMISSION_DENIED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LABORATORY_CONTENT,
    MODEL_LABORATORY_FILE,
    MODEL_LOCK_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_REPORT_TEMPLATE,
    MODEL_REPORT_TEMPLATE_VERSION,
    MODEL_TEST_REPORT,
)
from odoo.addons.sol_laboratory.constants.report_templates import BLOCK_BINDINGS, DRAFT, SCALAR_BINDINGS
from odoo.addons.sol_laboratory.constants.xml_ids import REPORT_TEMPLATES_FOLDER
from odoo.addons.sol_laboratory.models.testing.test_report import PRINT_LANGS
from odoo.addons.sol_laboratory.services import report_docx
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_report_template as ReportTemplateBase
else:
    ReportTemplateBase = object

# Characters a file name cannot hold.
NOT_IN_FILE_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
# The label of each binding in a new template, by the key of the report's printed labels.
BINDING_LABELS = {
    "report_number": "number",
    "report_date": "date",
    "request_code": "request",
    "customer_name": "customer",
    "customer_address": "address",
    "received_dates": "received",
    "samples": "results",
    "approvers": "signatures",
}


# Mẫu Phiếu Kết Quả
class ReportTemplate(models.Model, ReportTemplateBase):
    _name = MODEL_REPORT_TEMPLATE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Report Template"
    _order = "sequence, id"
    # A template is never deleted; its versions are archived.
    _permission_actions = ("read", "create", "edit")
    _audit_children = ("version_ids",)

    if not TYPE_CHECKING:
        # Name administrators know the template by, such as Water testing report.
        name = fields.Char(required=True)
        # Language of the reports the template prints: Vietnamese, English or both side by side.
        language = fields.Selection(
            [("vi", "Vietnamese"), ("en", "English"), ("bilingual", "Bilingual")], required=True
        )
        # Order in which new reports of the language pick their template: the first with an available version.
        sequence = fields.Integer(default=10)
        # The DOCX file the template is edited in; its versions are the template's saves.
        file_id = fields.Many2one(
            MODEL_LABORATORY_FILE, string="DOCX File", readonly=True, copy=False, ondelete="restrict"
        )
        # Every version of the template, the latest first.
        version_ids = fields.One2many(
            MODEL_REPORT_TEMPLATE_VERSION, "template_id", string="Versions", context={"active_test": False}
        )

    _file_unique = models.Constraint("UNIQUE(file_id)", "A DOCX file belongs to one report template.")

    @api.model_create_multi
    def create(self, vals_list):
        """A new template starts with a first draft version, holding every binding after its label in the template's
        language, for the administrator to lay out in the editor."""
        templates = super().create(vals_list)
        folder = self.env.ref(REPORT_TEMPLATES_FOLDER)
        files = self.env[MODEL_LABORATORY_FILE].sudo()
        for template in templates.sudo():
            name = NOT_IN_FILE_NAME.sub("-", template.name or "").strip(" .-") or str(template.id)
            template.file_id = files._get_or_create(folder, f"{template.id}/{name}.docx")
            self.env[MODEL_REPORT_TEMPLATE_VERSION].sudo().create({"template_id": template.id, "number": 1})
            template.file_id._add_version(
                content=self.env[MODEL_LABORATORY_CONTENT]._store_bytes(template._starter()),
                source=GENERATED,
                user=self.env.user,
            )
        return templates

    def write(self, vals):
        if "file_id" in vals and not self.env.su:
            raise UserError(self.env._("A template keeps the DOCX file it was created with."))
        if "language" in vals and any(template.language != vals["language"] for template in self):
            raise UserError(self.env._("A template keeps its language; create another template for another language."))
        return super().write(vals)

    def _starter(self):
        """The DOCX a new template starts from: its title and each binding under its label, in its languages."""
        self.ensure_one()
        reports = self.env[MODEL_TEST_REPORT]
        labels = reports._labels_in(PRINT_LANGS[self.language or ""])
        return report_docx.starter(
            labels["title"],
            {name: labels[BINDING_LABELS[name]] for name in SCALAR_BINDINGS},
            {name: labels[BINDING_LABELS[name]] for name in BLOCK_BINDINGS},
        )

    def _draft_version(self):
        self.ensure_one()
        return self.sudo().version_ids.filtered(lambda version: version.state == DRAFT)[:1]

    def _check_docx_access(self, access):
        """Refuse the user reading the template's DOCX without permission to read template versions, or writing it
        without permission to edit them or while it has no draft version."""
        if not self.env[MODEL_REPORT_TEMPLATE_VERSION]._has_permission("read" if access == FILE_READ else "edit"):
            raise LaboratoryFileError(
                PERMISSION_DENIED, self.env._("You do not have permission to open this report template.")
            )
        if access != FILE_READ:
            self._check_docx_writable()

    def _check_docx_writable(self):
        if not self._draft_version():
            raise LaboratoryFileError(
                LOCKED, self.env._("This template has no draft version; create one from its available version first.")
            )
