from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools import format_list

from odoo.addons.sol_inventory.constants.models import MODEL_SCRAP_REASON_TAG, MODEL_STOCK_MOVE
from odoo.addons.sol_inventory.constants.xml_ids import SCRAP_EXPIRED
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN

LISTED_MOVES = 10


# Lý Do Loại Bỏ
class StockScrapReasonTag(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_SCRAP_REASON_TAG
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_SCRAP_REASON_TAG]

    @api.ondelete(at_uninstall=False)
    def _unlink_except_named(self):
        # Every disposal names Expired. A move is never changed, so a reason stays while a move names it.
        expired = self.env.ref(SCRAP_EXPIRED, raise_if_not_found=False)
        if expired and expired in self:
            raise UserError(self.env._("Expired is the reason of every disposal, so it cannot be deleted."))
        moves = self.env[MODEL_STOCK_MOVE].sudo().search([("scrap_reason_tag_ids", "in", self.ids)], limit=LISTED_MOVES)
        if moves:
            raise UserError(
                self.env._(
                    "These reasons cannot be deleted while moves name them: %s",
                    format_list(self.env, moves.mapped("reference")),
                )
            )
