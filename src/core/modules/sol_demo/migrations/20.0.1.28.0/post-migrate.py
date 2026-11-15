from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_demo.demo_mandatory_notices import seed_mandatory_notices


def migrate(cr, _version):
    seed_mandatory_notices(api.Environment(cr, SUPERUSER_ID, {}))
