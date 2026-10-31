from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE_CHANGE,
    MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_file_change as LaboratoryFileChangeSampleBase
else:
    LaboratoryFileChangeSampleBase = object


# Thay Đổi Tệp: the changes of a sample's folder only for people who see the sample.
class LaboratoryFileChangeSample(models.Model, LaboratoryFileChangeSampleBase):
    _name = MODEL_LABORATORY_FILE_CHANGE
    _inherit = [MODEL_LABORATORY_FILE_CHANGE, MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN]
