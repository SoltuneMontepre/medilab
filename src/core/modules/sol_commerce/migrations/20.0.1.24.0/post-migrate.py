from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import STATUS_CONFIRMED


# A test request held for its order's balance is released once the order's advance is verified.
def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env[MODEL_SALE_ORDER].search(
        [("order_status", "=", STATUS_CONFIRMED), ("test_request_id.status", "=", "confirmed")]
    )
    orders.filtered(lambda order: order._can_collect_samples())._release_test_request()
