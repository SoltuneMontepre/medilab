from typing import TYPE_CHECKING

from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_PERMISSION_MIXIN,
    MODEL_REPORT_TEMPLATE_VERSION,
    MODEL_TEST_REPORT,
    MODEL_TEST_REPORT_DRAFT,
    MODEL_TEST_RESULT,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_report_draft as TestReportDraftBase
else:
    TestReportDraftBase = object


# Bản Nháp Phiếu Kết Quả: one generation of a report's working DOCX from a template version and approved business
# data. The editors' saves after it are versions of the same DOCX file.
class TestReportDraft(models.Model, TestReportDraftBase):
    _name = MODEL_TEST_REPORT_DRAFT
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Test Report Draft"
    _order = "id desc"
    # Generating a report's draft makes them; they never change.
    _permission_actions = ("read",)

    if not TYPE_CHECKING:
        # The report generated.
        report_id = fields.Many2one(
            MODEL_TEST_REPORT, string="Report", required=True, readonly=True, ondelete="restrict", index=True
        )
        # The exact template version the DOCX was generated from.
        template_version_id = fields.Many2one(
            MODEL_REPORT_TEMPLATE_VERSION, string="Template Version", required=True, readonly=True, ondelete="restrict"
        )
        # The DOCX version generated.
        docx_version_id = fields.Many2one(
            MODEL_LABORATORY_FILE_VERSION, string="DOCX", required=True, readonly=True, ondelete="restrict"
        )
        # The approved result versions the DOCX prints.
        result_ids = fields.Many2many(
            MODEL_TEST_RESULT,
            "medilab_test_report_draft_result_rel",
            "draft_id",
            "result_id",
            string="Results",
            readonly=True,
        )
        # The values the DOCX's bindings were filled with, by binding name.
        snapshot = fields.Json(readonly=True)

    def write(self, vals):
        if vals:
            raise UserError(self.env._("A generated draft never changes; generate the report's draft again instead."))
        return super().write(vals)
