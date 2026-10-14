from odoo import api, models

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY, MODEL_RES_USERS


# Tài Khoản
class ResUsers(models.Model):
    _inherit = MODEL_RES_USERS

    @api.model
    def _update_last_login(self):
        # Odoo writes its login log here, once the password is checked.
        result = super()._update_last_login()
        self.env[MODEL_AUDIT_ENTRY]._log_session("login")
        return result
