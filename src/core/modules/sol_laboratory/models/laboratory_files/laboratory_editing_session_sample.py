from odoo import models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_EDITING_SESSION,
    MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN,
)


# Phiên Chỉnh Sửa Trực Tuyến: the editing sessions of a sample's folder only for people who see the sample.
class LaboratoryEditingSessionSample(models.Model):
    _name = MODEL_LABORATORY_EDITING_SESSION
    _inherit = [MODEL_LABORATORY_EDITING_SESSION, MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN]
    _sample_field = "file_id.folder_id.sample_id"
