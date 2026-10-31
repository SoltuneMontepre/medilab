from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_DEPARTMENT, MODEL_IR_UI_MENU
from odoo.addons.sol_laboratory.constants.xml_ids import DEPARTMENTS_MENU

if TYPE_CHECKING:
    from medilab_model_types import Model_ir_ui_menu as IrUiMenuBase
else:
    IrUiMenuBase = object


# Menu
class IrUiMenu(models.Model, IrUiMenuBase):
    _inherit = MODEL_IR_UI_MENU

    def _load_menus_blacklist(self):
        # Odoo shows Departments only to employee officers and department managers; the read permission shows it too.
        result = super()._load_menus_blacklist()
        menu_id = self.env.ref(DEPARTMENTS_MENU).id
        if menu_id in result and self.env[MODEL_DEPARTMENT]._has_permission("read"):
            result.remove(menu_id)
        return result
