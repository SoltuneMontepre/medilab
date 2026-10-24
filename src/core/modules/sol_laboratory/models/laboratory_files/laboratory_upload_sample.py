from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN, MODEL_LABORATORY_UPLOAD


# Tải Lên Tệp: the uploads to a sample's folder only for people who see the sample.
class LaboratoryUploadSample(models.Model):
    _name = MODEL_LABORATORY_UPLOAD
    _inherit = [MODEL_LABORATORY_UPLOAD, MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN]
