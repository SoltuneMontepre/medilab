from odoo import models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE_CHANGE,
    MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN,
)


# Thay Đổi Tệp: the changes of a sample's folder only for people who see the sample.
class LaboratoryFileChangeSample(models.Model):
    _name = MODEL_LABORATORY_FILE_CHANGE
    _inherit = [MODEL_LABORATORY_FILE_CHANGE, MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN]
