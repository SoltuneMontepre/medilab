from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_laboratory.constants.models import MODEL_TASK


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    tasks = env[MODEL_TASK].search([("planned_start", "!=", False), ("status", "not in", ("done", "cancelled"))])
    tasks._sync_calendar_event()
