from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN, MODEL_LABORATORY_SYNC_RULE


# Quy Tắc Đồng Bộ: the rules of a sample's folder only for people who see the sample.
class LaboratorySyncRuleSample(models.Model):
    _name = MODEL_LABORATORY_SYNC_RULE
    _inherit = [MODEL_LABORATORY_SYNC_RULE, MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN]
