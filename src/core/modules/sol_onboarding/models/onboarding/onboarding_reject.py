from odoo import api, fields, models

from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_REJECT, MODEL_ONBOARDING_STAGED_RECORD


# Từ Chối Bản Ghi Chờ Duyệt
class OnboardingReject(models.TransientModel):
    _name = MODEL_ONBOARDING_REJECT
    _description = "Reject Staged Records"

    # The staged records to reject.
    staged_record_ids = fields.Many2many(MODEL_ONBOARDING_STAGED_RECORD, string="Staged Records")
    # Why they are rejected; optional.
    reason = fields.Text(string="Reason")

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if (
            "staged_record_ids" in fields_list
            and self.env.context.get("active_model") == MODEL_ONBOARDING_STAGED_RECORD
        ):
            defaults["staged_record_ids"] = self.env.context.get("active_ids", [])
        return defaults

    def action_confirm(self):
        self.ensure_one()
        self.staged_record_ids.action_reject(self.reason)
