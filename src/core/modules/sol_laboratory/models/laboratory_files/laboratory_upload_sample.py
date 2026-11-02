from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN, MODEL_LABORATORY_UPLOAD

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_upload as LaboratoryUploadSampleBase
else:
    LaboratoryUploadSampleBase = object


# Tải Lên Tệp: the uploads to a sample's folder only for people who see the sample.
class LaboratoryUploadSample(models.Model, LaboratoryUploadSampleBase):
    _name = MODEL_LABORATORY_UPLOAD
    _inherit = [MODEL_LABORATORY_UPLOAD, MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN]
