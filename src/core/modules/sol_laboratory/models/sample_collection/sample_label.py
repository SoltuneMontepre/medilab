from typing import TYPE_CHECKING

from odoo import api, models

from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE, MODEL_SAMPLE_LABEL

if TYPE_CHECKING:
    from medilab_model_types import Model_report_sol_laboratory_report_sample_label as SampleLabelBase
else:
    SampleLabelBase = object


# Tem Mẫu
class SampleLabel(models.AbstractModel, SampleLabelBase):
    _name = MODEL_SAMPLE_LABEL
    _description = "Sample Label"

    @api.model
    def _get_report_values(self, docids, data=None):
        samples = self.env[MODEL_SAMPLE].browse(docids)._samples_for_labels()
        return {"doc_ids": samples.ids, "doc_model": MODEL_SAMPLE, "docs": samples}
