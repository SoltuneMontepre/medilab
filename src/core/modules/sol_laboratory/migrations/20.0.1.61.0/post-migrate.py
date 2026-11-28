from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_AUTHORIZATION, MODEL_TASK
from odoo.addons.sol_laboratory.constants.tasks import FINAL_STATUSES

REASON = "Moved back to the department of its way of testing."


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    tasks = env[MODEL_TASK]
    authorizations = env[MODEL_PARAMETER_AUTHORIZATION]
    for task in tasks.search(tasks._testing_domain() & Domain("status", "not in", FINAL_STATUSES)):
        department = task._way_department()
        if not department or task.department_id == department:
            continue
        vals = {"department_id": department.id, "reassign_reason": REASON}
        assignee = task.assignee_id
        if assignee and (
            assignee.department_id != department or not authorizations._authorized(assignee, task._parameter())
        ):
            vals.update(assignee_id=False, assigned_by_id=False, status="open")
        task.write(vals)
