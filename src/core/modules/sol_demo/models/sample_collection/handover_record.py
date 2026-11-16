from datetime import timedelta
from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_HANDOVER_RECORD
from odoo.addons.sol_laboratory.services.model_lookup import reference_as

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_handover_record as HandoverRecordBase
else:
    HandoverRecordBase = object

# The handover records the customer signed on the sample delivery staff's phone, by the end of their xml id, with how
# long ago they signed.
SIGNED_AGO = {
    "fewer": timedelta(hours=3),
    "excess": timedelta(days=40),
}


# Biên Bản Giao Nhận Mẫu
class HandoverRecord(models.Model, HandoverRecordBase):
    _inherit = MODEL_HANDOVER_RECORD

    @api.model
    def _seed_signatures_demo(self):
        """Sign the handover records of fewer and of excess samples with their signature. An upgrade skips a data
        file's change to a record it created, so signing runs here. Safe to run again."""
        now = fields.Datetime.now()
        device = self.env.ref("sol_demo.demo_mobile_device_sample_delivery_staff")
        for name, ago in SIGNED_AGO.items():
            record = reference_as(self.env[MODEL_HANDOVER_RECORD], f"sol_demo.demo_handover_record_{name}")
            if record.status != "draft":
                continue
            signature = self.env.ref(f"sol_demo.demo_ir_attachment_handover_{name}_signature")
            record.sudo().write(
                {
                    "status": "signed",
                    "signed_at": now - ago,
                    "signed_device_id": device.id,
                    "signature_attachment_id": signature.id,
                }
            )
