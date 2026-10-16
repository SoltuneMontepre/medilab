from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_demo.demo_order_templates import seed_order_templates


def migrate(cr, _version):
    seed_order_templates(api.Environment(cr, SUPERUSER_ID, {}))
