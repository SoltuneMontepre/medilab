from typing import TYPE_CHECKING

from odoo import api, models

from odoo.addons.sol_laboratory.constants.laboratory_editing import CALLBACK_AUDIT_CONTEXT, CALLBACK_AUDIT_ORIGIN
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_audit_entry as AuditEntryBase
else:
    AuditEntryBase = object


# Nhật Ký Hoạt Động: a checked service callback has no browser actor; its model notes name the actual editors.
class AuditEntry(models.Model, AuditEntryBase):
    _inherit = MODEL_AUDIT_ENTRY

    @api.model
    def _origin_values(self):
        if self.env.context.get(CALLBACK_AUDIT_CONTEXT) is CALLBACK_AUDIT_ORIGIN:
            return {"source": "api", "user_id": False}
        return super()._origin_values()
