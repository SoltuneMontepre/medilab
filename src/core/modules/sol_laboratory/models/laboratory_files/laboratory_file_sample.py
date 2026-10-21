from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FILE, MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN


# Tệp Phòng Thí Nghiệm: the files of a sample's folder only for people who see the sample.
class LaboratoryFileSample(models.Model):
    _name = MODEL_LABORATORY_FILE
    _inherit = [MODEL_LABORATORY_FILE, MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN]
