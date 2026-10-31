from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.audit import MASK_SECRET
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_IR_CONFIG_PARAMETER

if TYPE_CHECKING:
    from medilab_model_types import Model_ir_config_parameter as IrConfigParameterBase
else:
    IrConfigParameterBase = object

# Odoo's own secret, kept in the system parameters; MediLab's secrets never reach them.
SECRET_PARAMETERS = frozenset({"database.secret"})


# Tham Số Hệ Thống
class IrConfigParameter(models.Model, IrConfigParameterBase):
    _name = MODEL_IR_CONFIG_PARAMETER
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_IR_CONFIG_PARAMETER]

    def _audit_notes(self):
        # The key names the setting even once the parameter is deleted.
        return {parameter.id: parameter.key for parameter in self.sudo()}

    def _audit_mask(self, field_name):
        if field_name == "value" and self.sudo().key in SECRET_PARAMETERS:
            return MASK_SECRET
        return super()._audit_mask(field_name)
