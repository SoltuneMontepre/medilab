from odoo import fields, models

from odoo.addons.sol_inventory.constants.models import (
    MODEL_PREPARATION_MAKE_CONTAINER,
    MODEL_PREPARATION_MAKE_LINE,
    MODEL_STOCK_PACKAGE,
)


# Chai đã quét cho một thành phần của lần pha.
class PreparationMakeContainer(models.TransientModel):
    _name = MODEL_PREPARATION_MAKE_CONTAINER
    _description = "Scanned Ingredient Container"
    _order = "sequence, id"

    # The ingredient line this container was scanned for.
    line_id = fields.Many2one(MODEL_PREPARATION_MAKE_LINE, required=True, ondelete="cascade")
    # The container that was scanned.
    container_id = fields.Many2one(MODEL_STOCK_PACKAGE, string="Container", required=True)
    # Place in the scan order. Earlier containers are used up first.
    sequence = fields.Integer(default=10)
