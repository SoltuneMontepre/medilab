from odoo import models

from odoo.addons.sol_commerce.constants.models import MODEL_CUSTOMER_SALES_TERMS, MODEL_SALE_ORDER
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REQUEST


# Yêu Cầu Thử Nghiệm: a request waits for its order's payment unless the customer may buy on credit.
class TestRequest(models.Model):
    _inherit = MODEL_TEST_REQUEST

    def _credit_blocks_confirmation(self):
        self.ensure_one()
        order = self.env[MODEL_SALE_ORDER].sudo().search([("test_request_id", "=", self.id)], limit=1)
        if not order or order._is_paid():
            return False
        terms = self.env[MODEL_CUSTOMER_SALES_TERMS].sudo().search([("customer_id", "=", self.customer_id.id)], limit=1)
        return not terms.allow_credit
