from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_commerce.hooks import use_vietnamese_accounting


def migrate(cr, _version):
    # A database installed before the hook has the generic chart in USD; move it while it has no accounting.
    use_vietnamese_accounting(api.Environment(cr, SUPERUSER_ID, {}))
