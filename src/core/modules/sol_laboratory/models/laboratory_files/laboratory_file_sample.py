from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FILE, MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_file as LaboratoryFileSampleBase
else:
    LaboratoryFileSampleBase = object


# Tệp Phòng Thí Nghiệm: the files of a sample's folder only for people who see the sample.
class LaboratoryFileSample(models.Model, LaboratoryFileSampleBase):
    _name = MODEL_LABORATORY_FILE
    _inherit = [MODEL_LABORATORY_FILE, MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN]
