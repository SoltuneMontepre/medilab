from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_commerce.hooks import use_vietnamese_accounting


def migrate(cr, _version):
    # A company already on the Vietnamese chart kept its price lists, and their orders, in another currency.
    use_vietnamese_accounting(api.Environment(cr, SUPERUSER_ID, {}))
