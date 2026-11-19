from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST, MODEL_TASK
from odoo.addons.sol_laboratory.constants.tasks import TESTING_ACTION


def migrate(cr, _version):
    # An outsourced test keeps no open in-house testing task: its subcontractor or a lab QA enters the result.
    env = api.Environment(cr, SUPERUSER_ID, {})
    outsourced = env[MODEL_SAMPLE_TEST].search([("status", "=", "outsourced")])
    env[MODEL_TASK]._cancel_for_document(outsourced, TESTING_ACTION)
