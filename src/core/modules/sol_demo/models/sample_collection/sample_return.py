from datetime import timedelta
from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_HANDOVER_RECORD, MODEL_SAMPLE_RETURN
from odoo.addons.sol_laboratory.services.model_lookup import reference_as

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample_return as SampleReturnBase
else:
    SampleReturnBase = object

# The handover records the customer signed on the sample delivery staff's phone, by the end of their xml id, with how
# long ago they signed.
SIGNED_AGO = {
    "fewer": timedelta(hours=3),
    "excess": timedelta(days=40),
}


# Trả Mẫu
class SampleReturn(models.Model, SampleReturnBase):
    _inherit = MODEL_SAMPLE_RETURN

    @api.model
    def _seed_signatures_demo(self):
        """Sign the handover records of fewer and of excess samples with their signature, as returning extras needs a
        signed record. An upgrade skips a data file's change to a record it created, so signing runs here. Safe to run
        again."""
        now = fields.Datetime.now()
        device = self.env.ref("sol_demo.demo_laboratory_device_sample_delivery_staff_phone")
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
