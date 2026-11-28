from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import ADVANCE_NONE, STATUS_COMPLETED, STATUS_CONFIRMED


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env[MODEL_SALE_ORDER].search(
        [
            ("order_status", "in", (STATUS_CONFIRMED, STATUS_COMPLETED)),
            ("advance_method", "=", ADVANCE_NONE),
            ("test_request_id", "!=", False),
            ("payment_request_ids", "=", False),
            ("on_credit", "=", False),
        ]
    )
    credit_orders = orders.filtered(lambda order: order._qualifies_for_credit(order.test_request_id.customer_id))
    credit_orders.on_credit = True
    # The old workflow marked an unpaid credit request Paid after confirmation.
    waiting = credit_orders.filtered(
        lambda order: order.test_request_id.status in ("confirmed", "paid") and order.payment_status != "paid"
    )
    waiting.test_request_id.status = "on_credit"
