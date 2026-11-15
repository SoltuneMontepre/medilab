from typing import TYPE_CHECKING

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import STATUS_COMPLETED, STATUS_CONFIRMED
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REQUEST

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_request as TestRequestBase
else:
    TestRequestBase = object


# Yêu Cầu Thử Nghiệm: a request waits for its order's payment unless the customer may buy on credit, and issuing its
# report completes the order.
class TestRequest(models.Model, TestRequestBase):
    _inherit = MODEL_TEST_REQUEST

    def _sale_order(self):
        """The order the request was made for; empty for a request the laboratory took without an order."""
        self.ensure_one()
        return self.env[MODEL_SALE_ORDER].sudo().search([("test_request_id", "=", self.id)], limit=1)

    def _credit_blocks_confirmation(self):
        self.ensure_one()
        order = self._sale_order()
        if not order:
            return False
        advance = order.payment_request_ids.filtered(
            lambda ask: ask.quotation_id == order._latest_quotation() and ask.kind == "advance"
        )
        return bool(advance and advance.state != "funded")

    def _status_after_confirmation(self):
        order = self._sale_order()
        if not order:
            return super()._status_after_confirmation()
        if order.on_credit:
            return "on_credit"
        return "paid" if order._can_collect_samples() else False

    def _check_sample_intake(self):
        for request in self:
            order = request._sale_order()
            if order.payment_request_id.kind == "balance" and not order._can_collect_samples():
                raise UserError(self.env._("Verify the order balance before collecting its samples."))
        return super()._check_sample_intake()

    def _set_status(self, status):
        result = super()._set_status(status)
        if status == "reported":
            for request in self:
                order = request._sale_order()
                if order.order_status == STATUS_CONFIRMED:
                    order._set_status(STATUS_COMPLETED)
        return result
