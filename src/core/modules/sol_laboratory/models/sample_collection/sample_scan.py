from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_HANDOVER, MODEL_SAMPLE_SCAN

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample_scan as SampleScanBase
else:
    SampleScanBase = object


# Quét Tem Mẫu
class SampleScan(models.TransientModel, SampleScanBase):
    _name = MODEL_SAMPLE_SCAN
    _description = "Scan Sample"

    if not TYPE_CHECKING:
        # Lab code read from the sample's label.
        code = fields.Char(string="Lab Code", required=True)

    def action_confirm(self):
        self.ensure_one()
        handover = self.env[MODEL_SAMPLE_HANDOVER].receive_by_label(self.code)
        return handover._get_records_action()
