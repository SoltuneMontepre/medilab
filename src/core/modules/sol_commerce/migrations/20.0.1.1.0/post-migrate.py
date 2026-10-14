from odoo import SUPERUSER_ID, api

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_CHANGE


def migrate(cr, _version):
    # Payer details recorded before the trail masked them in part are masked the same way.
    env = api.Environment(cr, SUPERUSER_ID, {})
    env[MODEL_AUDIT_CHANGE]._mask_recorded_values()
