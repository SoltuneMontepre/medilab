from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE_LOCK,
    MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_file_lock as LaboratoryFileLockSampleBase
else:
    LaboratoryFileLockSampleBase = object


# Khóa Tệp Phòng Thí Nghiệm: the locks of a sample's folder only for people who see the sample.
class LaboratoryFileLockSample(models.Model, LaboratoryFileLockSampleBase):
    _name = MODEL_LABORATORY_FILE_LOCK
    _inherit = [MODEL_LABORATORY_FILE_LOCK, MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN]
