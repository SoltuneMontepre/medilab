from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN

# Odoo's own secret, kept in the system parameters; MediLab's secrets never reach them.
SECRET_PARAMETERS = frozenset({"database.secret"})


# Tham Số Hệ Thống
class IrConfigParameter(models.Model):
    # Odoo needs the name of a model it adds a parent to.
    _name = "ir.config_parameter"
    _inherit = ["ir.config_parameter", MODEL_AUDIT_MIXIN]

    def _audit_notes(self):
        # The key names the setting even once the parameter is deleted.
        return {parameter.id: parameter.key for parameter in self.sudo()}

    def _audit_masked(self, field_name):
        return (field_name == "value" and self.sudo().key in SECRET_PARAMETERS) or super()._audit_masked(field_name)
