from odoo import api, models

from odoo.addons.sol_laboratory.constants.laboratory_editing import CALLBACK_AUDIT_CONTEXT, CALLBACK_AUDIT_ORIGIN
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY


# Nhật Ký Hoạt Động: a checked service callback has no browser actor; its model notes name the actual editors.
class AuditEntry(models.Model):
    _inherit = MODEL_AUDIT_ENTRY

    @api.model
    def _origin_values(self):
        if self.env.context.get(CALLBACK_AUDIT_CONTEXT) is CALLBACK_AUDIT_ORIGIN:
            return {"source": "api", "user_id": False}
        return super()._origin_values()
