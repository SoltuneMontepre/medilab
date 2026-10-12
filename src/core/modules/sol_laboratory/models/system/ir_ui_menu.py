from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_DEPARTMENT
from odoo.addons.sol_laboratory.constants.xml_ids import DEPARTMENTS_MENU


# Menu
class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    def _load_menus_blacklist(self):
        # Odoo shows Departments only to employee officers and department managers; the read permission shows it too.
        result = super()._load_menus_blacklist()
        menu_id = self.env.ref(DEPARTMENTS_MENU).id
        if menu_id in result and self.env[MODEL_DEPARTMENT]._has_permission("read"):
            result.remove(menu_id)
        return result
