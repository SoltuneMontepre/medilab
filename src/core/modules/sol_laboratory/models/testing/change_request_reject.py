from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_CHANGE_REQUEST, MODEL_CHANGE_REQUEST_REJECT


# Từ Chối Yêu Cầu Thay Đổi
class ChangeRequestReject(models.TransientModel):
    _name = MODEL_CHANGE_REQUEST_REJECT
    _description = "Reject a Change Request"

    # The change request rejected.
    change_request_id = fields.Many2one(MODEL_CHANGE_REQUEST, required=True, ondelete="cascade")
    # Why the request is rejected; the requester receives it.
    reason = fields.Text(required=True)

    def action_reject(self):
        self.ensure_one()
        self.change_request_id.action_reject(self.reason)
        return {"type": "ir.actions.act_window_close"}
