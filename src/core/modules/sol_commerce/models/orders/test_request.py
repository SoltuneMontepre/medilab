from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import STATUS_COMPLETED, STATUS_CONFIRMED
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REQUEST

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_request as TestRequestBase
else:
    TestRequestBase = object


# Yêu Cầu Thử Nghiệm: issuing a test request's report completes its sale order.
class TestRequest(models.Model, TestRequestBase):
    _inherit = MODEL_TEST_REQUEST

    def _sale_order(self):
        """The order the request was made for; empty for a request the laboratory took without an order."""
        self.ensure_one()
        return self.env[MODEL_SALE_ORDER].sudo().search([("test_request_id", "=", self.id)], limit=1)

    def _set_status(self, status):
        result = super()._set_status(status)
        if status == "reported":
            for request in self:
                order = request._sale_order()
                if order.order_status == STATUS_CONFIRMED:
                    order._set_status(STATUS_COMPLETED)
        return result
