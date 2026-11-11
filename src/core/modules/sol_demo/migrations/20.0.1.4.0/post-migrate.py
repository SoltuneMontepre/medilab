from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_demo.demo_laboratory_files import seed_laboratory_file_restores


def migrate(cr, _version):
    seed_laboratory_file_restores(api.Environment(cr, SUPERUSER_ID, {}))
