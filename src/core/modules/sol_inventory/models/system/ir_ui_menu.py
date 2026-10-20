from odoo import models

from odoo.addons.sol_inventory.constants.xml_ids import STOCK_MANAGER_GROUP, STOCK_REPORTING_MENU, STOCK_SCREEN_MENUS
from odoo.addons.sol_laboratory.constants.models import MODEL_IR_UI_MENU


# Menu
class IrUiMenu(models.Model):
    _inherit = MODEL_IR_UI_MENU

    def _load_menus_blacklist(self):
        # Holders of the stock read permission open Reporting for the stock screens. The reports other apps add under
        # it, such as the returns of sale_stock, see every store, so they stay with Odoo's stock managers.
        result = super()._load_menus_blacklist()
        if self.env.user.has_group(STOCK_MANAGER_GROUP):
            return result
        reporting = self.env.ref(STOCK_REPORTING_MENU)
        screens = [self.env.ref(xml_id).id for xml_id in STOCK_SCREEN_MENUS]
        return result + [menu.id for menu in reporting.sudo().child_id if menu.id not in screens]
