from odoo import models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE_LOCK,
    MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN,
)


# Khóa Tệp Phòng Thí Nghiệm: the locks of a sample's folder only for people who see the sample.
class LaboratoryFileLockSample(models.Model):
    _name = MODEL_LABORATORY_FILE_LOCK
    _inherit = [MODEL_LABORATORY_FILE_LOCK, MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN]
