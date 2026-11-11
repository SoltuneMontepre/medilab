from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_demo.demo_orders import seed_request_orders


def migrate(cr, _version):
    seed_request_orders(api.Environment(cr, SUPERUSER_ID, {}))
