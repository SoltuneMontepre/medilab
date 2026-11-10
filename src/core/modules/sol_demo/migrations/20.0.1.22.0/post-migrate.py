from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_demo.demo_report_templates import seed_report_templates


def migrate(cr, _version):
    seed_report_templates(api.Environment(cr, SUPERUSER_ID, {}))
