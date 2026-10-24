from odoo import models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN,
)


# Phiên Bản Tệp: the versions of a sample's folder only for people who see the sample.
class LaboratoryFileVersionSample(models.Model):
    _name = MODEL_LABORATORY_FILE_VERSION
    _inherit = [MODEL_LABORATORY_FILE_VERSION, MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN]
    _sample_field = "file_id.folder_id.sample_id"
