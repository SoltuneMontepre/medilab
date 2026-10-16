from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_CHANGE_REQUEST, MODEL_CHANGE_REQUEST_RAISE


# Tạo Yêu Cầu Thay Đổi
class ChangeRequestRaise(models.TransientModel):
    _name = MODEL_CHANGE_REQUEST_RAISE
    _description = "Raise a Change Request"

    # Technical name of the document to change.
    document_model = fields.Char(required=True)
    # Id of the version of the document to change.
    document_id = fields.Many2oneReference(model_field="document_model", required=True)
    # What to change.
    requested_change = fields.Text(string="Change", required=True)
    # Why the change is needed.
    reason = fields.Text(required=True)

    def action_raise(self):
        self.ensure_one()
        request = self.env[MODEL_CHANGE_REQUEST]._raise(
            self.document_model, self.document_id, self.requested_change, self.reason
        )
        return request._get_records_action()
