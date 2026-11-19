from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_demo.demo_dispatch_delivery import seed_dispatch_delivery


def migrate(cr, _version):
    seed_dispatch_delivery(api.Environment(cr, SUPERUSER_ID, {}))
