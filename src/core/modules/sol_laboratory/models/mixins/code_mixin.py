from typing import TYPE_CHECKING

from odoo import api, models

from odoo.addons.sol_laboratory.constants.models import MODEL_CODE_MIXIN

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_code_mixin as CodeMixinBase
else:
    CodeMixinBase = object


# Fills an empty code from the sequence whose code is the model's name.
class CodeMixin(models.AbstractModel, CodeMixinBase):
    _name = MODEL_CODE_MIXIN
    _description = "Code from a Sequence"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code"):
                vals["code"] = self.env["ir.sequence"].next_by_code(self._name)
        return super().create(vals_list)
