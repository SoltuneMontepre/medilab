from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_demo.demo_dispatches import seed_same_method_outsourcing


def migrate(cr, _version):
    seed_same_method_outsourcing(api.Environment(cr, SUPERUSER_ID, {}))
