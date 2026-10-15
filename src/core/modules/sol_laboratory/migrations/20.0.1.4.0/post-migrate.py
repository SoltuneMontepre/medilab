from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_CHANGE


def migrate(cr, _version):
    # Personal data recorded before the trail masked it in part is masked the same way.
    env = api.Environment(cr, SUPERUSER_ID, {})
    env[MODEL_AUDIT_CHANGE]._mask_recorded_values()
