from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_demo.demo_signing_levels import seed_signing_levels


def migrate(cr, _version):
    seed_signing_levels(api.Environment(cr, SUPERUSER_ID, {}))
