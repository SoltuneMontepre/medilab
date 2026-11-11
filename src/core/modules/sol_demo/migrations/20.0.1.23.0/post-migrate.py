from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_demo.demo_dispatches import seed_agreed_outsourcing


def migrate(cr, _version):
    seed_agreed_outsourcing(api.Environment(cr, SUPERUSER_ID, {}))
