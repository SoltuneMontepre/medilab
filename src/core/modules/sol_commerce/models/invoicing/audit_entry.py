from typing import TYPE_CHECKING

from odoo import api, models

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_audit_entry as AuditEntryBase
else:
    AuditEntryBase = object

# PayOS calls this route to report a transfer.
PAYOS_WEBHOOK_PATH = "/payment/payos/webhook"


# Mục Nhật Ký Hoạt Động
class AuditEntry(models.Model, AuditEntryBase):
    _inherit = MODEL_AUDIT_ENTRY

    @api.model
    def _api_path_prefixes(self):
        return (*super()._api_path_prefixes(), PAYOS_WEBHOOK_PATH)
