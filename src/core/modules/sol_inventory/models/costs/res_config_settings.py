from odoo import fields, models

from odoo.addons.sol_inventory.constants.models import MODEL_PRODUCT_CATEGORY
from odoo.addons.sol_inventory.constants.settings import (
    COSTING_FIFO,
    COSTING_METHOD_PARAMETER,
    COSTING_MOVING_AVERAGE,
    DEFAULT_COSTING_METHOD,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS


# Cài Đặt
class ResConfigSettings(models.TransientModel):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    # How stock is costed: first in, first out, or moving average.
    costing_method = fields.Selection(
        [(COSTING_FIFO, "First In, First Out"), (COSTING_MOVING_AVERAGE, "Moving Average")],
        config_parameter=COSTING_METHOD_PARAMETER,
        default=DEFAULT_COSTING_METHOD,
        required=True,
        help="First in, first out costs each container at its lot's price and other stock at its oldest receipts. "
        "Moving average costs stock at the average price of the item's stock. Moves already done keep their cost.",
    )

    def set_values(self):
        result = super().set_values()
        self.env[MODEL_PRODUCT_CATEGORY]._apply_costing_method(self._get_parameter("costing_method"))
        return result
