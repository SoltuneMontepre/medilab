from datetime import datetime, time
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from odoo import api, fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER, MODEL_SAMPLE_COLLECTION_START

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample_collection_start as SampleCollectionStartBase
else:
    SampleCollectionStartBase = object


# Bắt Đầu Thu Mẫu
class SampleCollectionStart(models.TransientModel, SampleCollectionStartBase):
    _name = MODEL_SAMPLE_COLLECTION_START
    _description = "Start Sample Collection"

    if not TYPE_CHECKING:
        # The confirmed order whose samples are collected.
        order_id = fields.Many2one(MODEL_SALE_ORDER, required=True, ondelete="cascade")
        # When sample delivery staff meet the customer to collect the samples.
        appointment = fields.Datetime(required=True)
        # Where the samples are collected; the customer's address unless Sales agreed another place.
        address = fields.Text(string="Collection Address", required=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        order = self.env[MODEL_SALE_ORDER].browse(values.get("order_id"))
        if order and "address" in fields_list and not values.get("address"):
            values["address"] = order.customer_id._display_address()
        if order.expected_collection_date and "appointment" in fields_list and not values.get("appointment"):
            values["appointment"] = self._pickup_appointment(order.expected_collection_date)
        return values

    def _pickup_appointment(self, day):
        """08:00 in the company's time zone on the pickup day agreed when sending the quotation, when still to come."""
        zone = ZoneInfo(self.env.company.tz or "UTC")
        start = datetime.combine(day, time(8), tzinfo=zone).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        return start if start > fields.Datetime.now() else False

    def action_start(self):
        self.ensure_one()
        notification = self.order_id.action_start_sample_collection(self.appointment, self.address)
        # Closing the dialog reloads the order, which then hides Start sample collection.
        notification["params"]["next"] = {"type": "ir.actions.act_window_close"}
        return notification
