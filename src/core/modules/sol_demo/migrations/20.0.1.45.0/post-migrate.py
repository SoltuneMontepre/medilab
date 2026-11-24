from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_demo.demo_orders import seed_report_payments


def migrate(cr, _version):
    seed_report_payments(api.Environment(cr, SUPERUSER_ID, {}))
