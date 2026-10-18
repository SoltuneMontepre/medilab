from odoo import fields, models

from odoo.addons.sol_inventory.constants.models import MODEL_CONTAINER_SCAN, MODEL_STOCK_PACKAGE


# Quét Chai
class ContainerScan(models.TransientModel):
    _name = MODEL_CONTAINER_SCAN
    _description = "Scan Container"

    # Code read from the container's label.
    code = fields.Char(string="Container Code", required=True)

    def action_confirm(self):
        self.ensure_one()
        container = self.env[MODEL_STOCK_PACKAGE]._find_by_code(self.code)
        return container.action_open()
