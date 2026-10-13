from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_IR_CONFIG_PARAMETER

# Odoo's own secret, kept in the system parameters; MediLab's secrets never reach them.
SECRET_PARAMETERS = frozenset({"database.secret"})


# Tham Số Hệ Thống
class IrConfigParameter(models.Model):
    _name = MODEL_IR_CONFIG_PARAMETER
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_IR_CONFIG_PARAMETER]

    def _audit_notes(self):
        # The key names the setting even once the parameter is deleted.
        return {parameter.id: parameter.key for parameter in self.sudo()}

    def _audit_masked(self, field_name):
        return (field_name == "value" and self.sudo().key in SECRET_PARAMETERS) or super()._audit_masked(field_name)
