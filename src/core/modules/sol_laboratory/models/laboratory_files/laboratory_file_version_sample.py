from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_file_version as LaboratoryFileVersionSampleBase
else:
    LaboratoryFileVersionSampleBase = object


# Phiên Bản Tệp: the versions of a sample's folder only for people who see the sample.
class LaboratoryFileVersionSample(models.Model, LaboratoryFileVersionSampleBase):
    _name = MODEL_LABORATORY_FILE_VERSION
    _inherit = [MODEL_LABORATORY_FILE_VERSION, MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN]
    _sample_field = "file_id.folder_id.sample_id"
