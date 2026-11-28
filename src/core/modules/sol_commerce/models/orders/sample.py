from typing import TYPE_CHECKING

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample as SampleBase
else:
    SampleBase = object


# Mẫu: hold sample intake while its sales order still owes the payment required before collection.
class Sample(models.Model, SampleBase):
    _inherit = MODEL_SAMPLE

    def action_receive(self, quantity, condition, condition_note=None, storage_location=None):
        for request in self.request_id.sudo():
            order = request._sale_order()
            hold = order and order._collection_hold()
            if hold:
                raise UserError(hold)
        return super().action_receive(
            quantity, condition, condition_note=condition_note, storage_location=storage_location
        )
