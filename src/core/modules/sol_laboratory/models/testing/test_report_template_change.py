from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_REPORT_TEMPLATE_VERSION,
    MODEL_TEST_REPORT,
    MODEL_TEST_REPORT_TEMPLATE_CHANGE,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_report_template_change as TestReportTemplateChangeBase
else:
    TestReportTemplateChangeBase = object


# Đổi Mẫu Phiếu Kết Quả
class TestReportTemplateChange(models.TransientModel, TestReportTemplateChangeBase):
    _name = MODEL_TEST_REPORT_TEMPLATE_CHANGE
    _description = "Change the Template of a Test Report"

    if not TYPE_CHECKING:
        # The report whose draft is generated again.
        report_id = fields.Many2one(MODEL_TEST_REPORT, required=True, ondelete="cascade")
        # The available template versions of the report's language, which the editor chooses from.
        available_version_ids = fields.Many2many(
            MODEL_REPORT_TEMPLATE_VERSION, compute="_compute_available_version_ids", compute_sudo=True
        )
        # The template version the draft is generated from.
        template_version_id = fields.Many2one(
            MODEL_REPORT_TEMPLATE_VERSION,
            string="Template Version",
            required=True,
            domain="[('id', 'in', available_version_ids)]",
        )

    @api.depends("report_id")
    def _compute_available_version_ids(self):
        for wizard in self:
            wizard.available_version_ids = wizard.report_id._template_versions()

    def action_apply(self):
        self.ensure_one()
        self.report_id._change_template(self.template_version_id)
        return {"type": "ir.actions.act_window_close"}
