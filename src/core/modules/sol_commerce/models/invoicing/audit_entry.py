from odoo import api, models

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY

# PayOS calls this route to report a transfer.
PAYOS_WEBHOOK_PATH = "/payment/payos/webhook"


# Mục Nhật Ký Hoạt Động
class AuditEntry(models.Model):
    _inherit = MODEL_AUDIT_ENTRY

    @api.model
    def _api_path_prefixes(self):
        return (*super()._api_path_prefixes(), PAYOS_WEBHOOK_PATH)
