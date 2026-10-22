from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_PARAMETER_METHOD,
    MODEL_SAMPLE_TEST,
    MODEL_SAMPLE_TEST_OUTSOURCE,
)


# Gửi Thầu Phụ Chỉ Tiêu Của Mẫu
class SampleTestOutsource(models.TransientModel):
    _name = MODEL_SAMPLE_TEST_OUTSOURCE
    _description = "Outsource a Sample Test"

    # The sample test sent to a subcontractor.
    sample_test_id = fields.Many2one(MODEL_SAMPLE_TEST, required=True, ondelete="cascade")
    # True when the scheduler suggests outsourcing the test; otherwise it is outsourced straight away.
    outsourcing_suggested = fields.Boolean(related="sample_test_id.outsourcing_suggested")
    # The subcontracted ways of testing it can go through.
    subcontracted_method_ids = fields.Many2many(related="sample_test_id.subcontracted_method_ids")
    # The way of testing it is sent through; the first subcontracted way by default.
    parameter_method_id = fields.Many2one(
        MODEL_PARAMETER_METHOD,
        string="Way of Testing",
        required=True,
        ondelete="cascade",
        compute="_compute_parameter_method_id",
        store=True,
        readonly=False,
        domain="[('id', 'in', subcontracted_method_ids)]",
    )
    # Why the test is outsourced straight away, without an outsourcing suggestion.
    reason = fields.Text()

    @api.depends("sample_test_id")
    def _compute_parameter_method_id(self):
        for wizard in self:
            wizard.parameter_method_id = wizard.sample_test_id.subcontracted_method_ids[:1]

    def action_outsource(self):
        self.ensure_one()
        # A test without a suggestion needs the reason; a reason given is never dropped.
        test = self.sample_test_id
        if self.reason or not test.outsourcing_suggested:
            dispatch = test._outsource_now(self.parameter_method_id, self.reason)
        else:
            dispatch = test._accept_outsourcing(self.parameter_method_id)
        return {
            "type": "ir.actions.act_window",
            "res_model": dispatch._name,
            "res_id": dispatch.id,
            "views": [(False, "form")],
        }
