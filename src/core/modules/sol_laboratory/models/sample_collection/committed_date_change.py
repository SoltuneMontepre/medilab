from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_COMMITTED_DATE_CHANGE,
    MODEL_PERMISSION_MIXIN,
    MODEL_TEST_REQUEST,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_committed_date_change as CommittedDateChangeBase
else:
    CommittedDateChangeBase = object

# Context key that lets a committed date change write the request's expected return date.
CHANGING_COMMITTED_DATE = "medilab_changing_committed_date"


# Thay Đổi Ngày Hẹn Trả Kết Quả
class CommittedDateChange(models.Model, CommittedDateChangeBase):
    _name = MODEL_COMMITTED_DATE_CHANGE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Committed Date Change"
    _order = "request_id, id desc"
    _permission_actions = ("read", "create")

    if not TYPE_CHECKING:
        # The test request whose expected return date changed.
        request_id = fields.Many2one(MODEL_TEST_REQUEST, required=True, ondelete="restrict", index=True)
        # The expected return date before the change.
        old_date = fields.Date(readonly=True)
        # The request's expected return date now, shown while the change is recorded.
        current_date = fields.Date(related="request_id.committed_date", string="Current Expected Return Date")
        # The expected return date after the change.
        new_date = fields.Date(string="New Expected Return Date", required=True)
        # How the customer confirmed the new date, such as the email or call it was agreed in.
        confirmation = fields.Text(string="Customer's Confirmation", required=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not (vals.get("confirmation") or "").strip():
                raise UserError(self.env._("Record how the customer agreed to the new date."))
            request = self.env[MODEL_TEST_REQUEST].browse(vals["request_id"])
            vals["old_date"] = request.committed_date
        changes = super().create(vals_list)
        for change in changes:
            change.request_id.sudo().with_context(**{CHANGING_COMMITTED_DATE: True}).committed_date = change.new_date
        return changes

    def write(self, vals):
        raise UserError(self.env._("A recorded change of a expected return date cannot be edited."))

    def unlink(self):
        raise UserError(self.env._("A recorded change of a expected return date cannot be deleted."))

    def action_record(self):
        # The form's button: saving the form records the change.
        return {"type": "ir.actions.act_window_close"}
