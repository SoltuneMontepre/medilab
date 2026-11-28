from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.settings import (
    DEFAULT_PAYMENT_DEADLINE_DAYS,
    DEFAULT_PRIORITY_MIN_DAYS,
    DEFAULT_PRIORITY_SURCHARGE,
    PAYMENT_DEADLINE_PARAMETER,
    PRIORITY_MIN_DAYS_PARAMETER,
    PRIORITY_ORDERS_OFF,
    PRIORITY_ORDERS_ON,
    PRIORITY_ORDERS_PARAMETER,
    PRIORITY_SURCHARGE_PARAMETER,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_res_config_settings as ResConfigSettingsBase
else:
    ResConfigSettingsBase = object


# Cài Đặt
class ResConfigSettings(models.TransientModel, ResConfigSettingsBase):
    _inherit = "res.config.settings"

    if not TYPE_CHECKING:
        # Days after sending before the quotation is flagged expired.
        payment_deadline_days = fields.Integer(
            config_parameter=PAYMENT_DEADLINE_PARAMETER,
            default=DEFAULT_PAYMENT_DEADLINE_DAYS,
            help="Days after a quotation is sent before it is flagged expired. "
            "Applies to quotations sent without a payment deadline.",
        )
        # Whether a requested date earlier than the standard return date makes a priority request.
        priority_orders = fields.Selection(
            [(PRIORITY_ORDERS_ON, "Offered"), (PRIORITY_ORDERS_OFF, "Not offered")],
            string="Priority Orders",
            config_parameter=PRIORITY_ORDERS_PARAMETER,
            default=PRIORITY_ORDERS_ON,
            required=True,
            help="Whether customers and Sales may ask for results earlier than the standard turnaround.",
        )
        # Working days from the expected pickup day to the earliest requested date a priority order may ask for.
        priority_min_turnaround_days = fields.Integer(
            string="Shortest Priority Turnaround (working days)",
            config_parameter=PRIORITY_MIN_DAYS_PARAMETER,
            default=DEFAULT_PRIORITY_MIN_DAYS,
            help="Working days from the expected sample pickup to the earliest date a priority order may ask for.",
        )
        # Percentage of the order's lines after their discounts, excluding VAT, an accepted priority order adds.
        priority_surcharge_percent = fields.Float(
            string="Priority Surcharge (%)",
            config_parameter=PRIORITY_SURCHARGE_PARAMETER,
            default=DEFAULT_PRIORITY_SURCHARGE,
            help="Added as a quotation line when Sales accepts a priority order: this percentage of the ordered lines "
            "after their discounts, excluding VAT. 0 adds no line. Applies to quotations not sent yet.",
        )

    @api.constrains("priority_min_turnaround_days")
    def _check_priority_min_turnaround(self):
        if any(settings.priority_min_turnaround_days < 1 for settings in self):
            raise ValidationError(self.env._("The shortest priority turnaround must be at least 1 working day."))

    @api.constrains("priority_surcharge_percent")
    def _check_priority_surcharge(self):
        if any(not 0 <= settings.priority_surcharge_percent <= 100 for settings in self):
            raise ValidationError(self.env._("The priority surcharge must be between 0% and 100%."))

    def set_values(self):
        super().set_values()
        # Quotations not sent yet follow the new settings; a sent quotation keeps its surcharge line.
        orders = self.env[MODEL_SALE_ORDER].sudo().search([("state", "=", "draft"), ("requested_date", "!=", False)])
        orders._sync_priority()
