from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER_LINE


# Quotation lines now take the tax of their parameter or package; the lines left without a tax on orders no quotation
# was sent for get theirs.
def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env[MODEL_SALE_ORDER_LINE]._tax_untaxed_drafts()
