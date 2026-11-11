from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER


# A quotation accepted without an advance read as paid; its order's follow-up now reads accepted.
def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env[MODEL_SALE_ORDER].search([("quotation_follow_up", "=", "paid")])
    env.add_to_compute(orders._fields["quotation_follow_up"], orders)
    env.flush_all()
