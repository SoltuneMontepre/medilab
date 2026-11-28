from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import BALANCE_BEFORE_COLLECTION, STATUS_CONFIRMED


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    waiting = env[MODEL_SALE_ORDER].search(
        [
            ("order_status", "=", STATUS_CONFIRMED),
            ("test_request_id.status", "=", "confirmed"),
            ("balance_due", "=", BALANCE_BEFORE_COLLECTION),
            ("on_credit", "=", False),
        ]
    )
    waiting._release_test_request()
