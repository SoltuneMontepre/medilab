from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REPORT, MODEL_TEST_REPORT_REJECT, MODEL_TEST_RESULT


# Từ Chối Phiếu Kết Quả
class TestReportReject(models.TransientModel):
    _name = MODEL_TEST_REPORT_REJECT
    _description = "Reject a Test Report"

    # The report rejected.
    report_id = fields.Many2one(MODEL_TEST_REPORT, required=True, ondelete="cascade")
    # The results printed on the report, which the lab head chooses from.
    available_result_ids = fields.Many2many(
        MODEL_TEST_RESULT, compute="_compute_available_result_ids", compute_sudo=True
    )
    # Why the report is rejected; the testing tasks of the results checked again carry it.
    reason = fields.Text(required=True)
    # The results to check again.
    result_ids = fields.Many2many(
        MODEL_TEST_RESULT, string="Results to Check Again", domain="[('id', 'in', available_result_ids)]"
    )

    @api.depends("report_id")
    def _compute_available_result_ids(self):
        for wizard in self:
            wizard.available_result_ids = wizard.report_id.result_ids

    def action_reject(self):
        self.ensure_one()
        self.report_id.action_reject(self.reason, self.result_ids)
        return {"type": "ir.actions.act_window_close"}
