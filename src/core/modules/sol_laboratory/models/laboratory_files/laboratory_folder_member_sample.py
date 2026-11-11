from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FOLDER_MEMBER,
    MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_folder_member as LaboratoryFolderMemberSampleBase
else:
    LaboratoryFolderMemberSampleBase = object


# Links a folder to a person: the members of a sample's folder only for people who see the sample.
class LaboratoryFolderMemberSample(models.Model, LaboratoryFolderMemberSampleBase):
    _name = MODEL_LABORATORY_FOLDER_MEMBER
    _inherit = [MODEL_LABORATORY_FOLDER_MEMBER, MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN]
