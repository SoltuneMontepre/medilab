from odoo import fields, models

from odoo.addons.sol_inventory.constants.models import MODEL_CONTAINER_OPENING, MODEL_STOCK_PACKAGE
from odoo.addons.sol_laboratory.constants.models import MODEL_RES_USERS


# Ghi Nhận Mở Nắp
class ContainerOpening(models.TransientModel):
    _name = MODEL_CONTAINER_OPENING
    _description = "Record Opening"

    # The sealed container someone opened.
    container_id = fields.Many2one(MODEL_STOCK_PACKAGE, string="Container", required=True, readonly=True)
    # Who opened the container.
    opened_by_id = fields.Many2one(MODEL_RES_USERS, string="Opened By", required=True, domain=[("share", "=", False)])
    # When the container was opened.
    opened_at = fields.Datetime(string="Opened At", required=True, default=fields.Datetime.now)
    # How the opening came about.
    note = fields.Char(required=True)

    def action_confirm(self):
        self.ensure_one()
        return self.container_id._record_opening(self.opened_by_id, self.opened_at, self.note)
