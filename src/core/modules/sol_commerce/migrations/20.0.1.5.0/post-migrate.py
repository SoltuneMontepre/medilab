from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import APPROVAL_REJECTED


def migrate(cr, _version):
    # Orders rejected before a rejection reopened them still hold their signatures; reopen them for sales.
    env = api.Environment(cr, SUPERUSER_ID, {})
    env[MODEL_SALE_ORDER].search([("approval_status", "=", APPROVAL_REJECTED)])._reopen_rejected()
