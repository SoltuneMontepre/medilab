import logging

from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_AUTHORIZATION, MODEL_TASK

_logger = logging.getLogger(__name__)

REASON = "Moved back to the department of its way of testing."


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    tasks = env[MODEL_TASK]
    authorizations = env[MODEL_PARAMETER_AUTHORIZATION]
    misplaced = tasks.search(tasks._testing_domain() & Domain("status", "in", ("open", "assigned", "in_progress")))
    for task in misplaced:
        department = task._way_department()
        if not department or task.department_id == department:
            continue
        if task.status == "in_progress":
            # A measurement already running stays with its tester; the head moves it once it is safe to.
            _logger.warning(
                "Testing task %s (%s) is in progress in %s, but %s tests it.",
                task.id,
                task.name,
                task.department_id.name,
                department.name,
            )
            continue
        vals = {"department_id": department.id, "reassign_reason": REASON}
        assignee = task.assignee_id
        if assignee and (
            assignee.department_id != department or not authorizations._authorized(assignee, task._parameter())
        ):
            vals.update(assignee_id=False, assigned_by_id=False, status="open")
        task.write(vals)
