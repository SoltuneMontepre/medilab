from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_LABORATORY_FILE_VERSION_REJECT,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_file_version_reject as LaboratoryFileVersionRejectBase
else:
    LaboratoryFileVersionRejectBase = object


# Từ Chối Phiên Bản Tệp
class LaboratoryFileVersionReject(models.TransientModel, LaboratoryFileVersionRejectBase):
    _name = MODEL_LABORATORY_FILE_VERSION_REJECT
    _description = "Reject a Laboratory File Version"

    if not TYPE_CHECKING:
        # The version rejected.
        version_id = fields.Many2one(MODEL_LABORATORY_FILE_VERSION, required=True, ondelete="cascade")
        # Why the version is rejected; the person who saved it receives it.
        reason = fields.Text(required=True)

    def action_reject(self):
        self.ensure_one()
        self.version_id.action_reject(self.reason)
        return {"type": "ir.actions.act_window_close"}
