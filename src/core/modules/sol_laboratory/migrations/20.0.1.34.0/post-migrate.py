from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REQUEST


def migrate(cr, _version):
    # Every test request now goes through the paid step, which its confirmation reaches at once; a request confirmed
    # before would otherwise wait at confirmed and never reach sample received.
    env = api.Environment(cr, SUPERUSER_ID, {})
    env[MODEL_TEST_REQUEST].search([("status", "=", "confirmed")])._set_status("paid")
