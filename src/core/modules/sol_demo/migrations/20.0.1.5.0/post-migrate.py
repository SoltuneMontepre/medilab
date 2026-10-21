from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_demo.demo_laboratory_uploads import seed_laboratory_uploads


def migrate(cr, _version):
    seed_laboratory_uploads(api.Environment(cr, SUPERUSER_ID, {}))
