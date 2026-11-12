from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST, MODEL_TASK
from odoo.addons.sol_laboratory.constants.tasks import TESTING_ACTION


def migrate(cr, _version):
    # Results are no longer counted by attempt; their required column would refuse every new result until the end of
    # the upgrade removes it.
    cr.execute("ALTER TABLE medilab_test_result DROP CONSTRAINT IF EXISTS medilab_test_result_attempt_unique")
    cr.execute("ALTER TABLE medilab_test_result DROP COLUMN IF EXISTS attempt")
    # A testing task is done once its result is submitted, so the tests already waiting for approval have theirs done.
    env = api.Environment(cr, SUPERUSER_ID, {})
    tests = env[MODEL_SAMPLE_TEST].search([("status", "=", "result_entered")])
    env[MODEL_TASK]._close_for_document(tests, TESTING_ACTION)
