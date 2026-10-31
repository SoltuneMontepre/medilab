from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_EDITING_SESSION,
    MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_editing_session as LaboratoryEditingSessionSampleBase
else:
    LaboratoryEditingSessionSampleBase = object


# Phiên Chỉnh Sửa Trực Tuyến: the editing sessions of a sample's folder only for people who see the sample.
class LaboratoryEditingSessionSample(models.Model, LaboratoryEditingSessionSampleBase):
    _name = MODEL_LABORATORY_EDITING_SESSION
    _inherit = [MODEL_LABORATORY_EDITING_SESSION, MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN]
    _sample_field = "file_id.folder_id.sample_id"
