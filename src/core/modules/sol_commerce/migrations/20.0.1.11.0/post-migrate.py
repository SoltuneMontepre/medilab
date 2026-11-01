from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER


def migrate(cr, _version):
    # The request of an order now goes through the paid step, which its confirmation reaches at once; a request
    # confirmed before would otherwise wait at confirmed and never reach sample received.
    env = api.Environment(cr, SUPERUSER_ID, {})
    env[MODEL_SALE_ORDER].search([("test_request_id.status", "=", "confirmed")]).test_request_id._set_status("paid")
