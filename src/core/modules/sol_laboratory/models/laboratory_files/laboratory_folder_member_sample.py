from odoo import models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FOLDER_MEMBER,
    MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN,
)


# Links a folder to a person: the members of a sample's folder only for people who see the sample.
class LaboratoryFolderMemberSample(models.Model):
    _name = MODEL_LABORATORY_FOLDER_MEMBER
    _inherit = [MODEL_LABORATORY_FOLDER_MEMBER, MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN]
