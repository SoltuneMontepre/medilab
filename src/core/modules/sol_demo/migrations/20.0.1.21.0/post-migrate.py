from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_demo.demo_notifications import seed_notifications


def migrate(cr, _version):
    seed_notifications(api.Environment(cr, SUPERUSER_ID, {}))
