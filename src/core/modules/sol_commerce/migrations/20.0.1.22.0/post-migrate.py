from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER


# The balance requested when an order sent without an advance was confirmed made its quotation read as paid; it now
# reads accepted.
def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env[MODEL_SALE_ORDER].search([("quotation_follow_up", "=", "paid")])
    env.add_to_compute(orders._fields["quotation_follow_up"], orders)
    env.flush_all()
