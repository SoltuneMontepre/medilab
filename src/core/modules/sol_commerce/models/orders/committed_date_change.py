from typing import TYPE_CHECKING

from odoo import api, models

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_laboratory.constants.models import MODEL_COMMITTED_DATE_CHANGE
from odoo.addons.sol_laboratory.models.sample_collection.committed_date_change import CHANGING_COMMITTED_DATE

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_committed_date_change as CommittedDateChangeBase
else:
    CommittedDateChangeBase = object


# Thay Đổi Ngày Hẹn Trả Kết Quả: the order of the request shows the new committed return date too.
class CommittedDateChange(models.Model, CommittedDateChangeBase):
    _inherit = MODEL_COMMITTED_DATE_CHANGE

    @api.model_create_multi
    def create(self, vals_list):
        changes = super().create(vals_list)
        for change in changes:
            orders = self.env[MODEL_SALE_ORDER].sudo().search([("test_request_id", "=", change.request_id.id)])
            orders.with_context(**{CHANGING_COMMITTED_DATE: True}).write({"committed_date": change.new_date})
        return changes
