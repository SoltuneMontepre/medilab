from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_HANDOVER, MODEL_SAMPLE_SCAN


# Quét Tem Mẫu
class SampleScan(models.TransientModel):
    _name = MODEL_SAMPLE_SCAN
    _description = "Scan Sample"

    # Lab code read from the sample's label.
    code = fields.Char(string="Lab Code", required=True)

    def action_confirm(self):
        self.ensure_one()
        handover = self.env[MODEL_SAMPLE_HANDOVER].receive_by_label(self.code)
        return handover._get_records_action()
