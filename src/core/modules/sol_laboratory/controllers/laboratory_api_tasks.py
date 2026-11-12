from odoo import http
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.medilab_mobile import ALREADY_CLAIMED, TASK_PAGE_SIZE
from odoo.addons.sol_laboratory.constants.models import MODEL_TASK
from odoo.addons.sol_laboratory.services.laboratory_api import laboratory_api_route
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.mobile_documents import not_found


def readable_task(env, task_id):
    """The task of the id once the person may read it; one they may not read is not found."""
    task = env[MODEL_TASK].browse(task_id).exists()
    if not task:
        raise not_found(env)
    task.check_access("read")
    return task


class LaboratoryApiTasks(http.Controller):
    """The person's day, to-do list and queues on Medilab Mobile, and the task actions the web's buttons take."""

    @laboratory_api_route("/tasks/today", ["GET"], "getTaskDay", permission=False)
    def get_day(self, device, _body):
        return device.env[MODEL_TASK]._mobile_day()

    @laboratory_api_route("/tasks", ["GET"], "listTasks", permission=False)
    def list_tasks(self, device, _body, **query):
        # The list's name comes as the query parameter list, which a Python argument cannot be named.
        limit = int(query.get("limit") or TASK_PAGE_SIZE)
        offset = int(query.get("after") or 0)
        tasks, more = device.env[MODEL_TASK]._mobile_list(query["list"], offset, limit)
        return {"tasks": tasks._mobile_values(), "next_after": offset + limit if more else None}

    @laboratory_api_route("/tasks", ["POST"], "createTask", permission=False)
    def create_task(self, device, body, idempotency_key=None):
        task = device.env[MODEL_TASK]._create_from_phone(device, body, idempotency_key)
        return task._mobile_detail()

    @laboratory_api_route("/tasks/assignees", ["GET"], "searchTaskAssignees", permission=False)
    def search_assignees(self, device, _body, q=""):
        return device.env[MODEL_TASK]._mobile_assignees(q)

    @laboratory_api_route("/tasks/<int:task_id>", ["GET"], "getTask", permission=False)
    def get_task(self, device, _body, task_id):
        return readable_task(device.env, task_id)._mobile_detail()

    @laboratory_api_route("/tasks/<int:task_id>/claim", ["POST"], "claimTask", permission=False)
    def claim_task(self, device, _body, task_id):
        # A task the person claims waits in their queue, which they read only while it is open: once someone else
        # claimed it, the claim itself says so.
        task = device.env[MODEL_TASK].browse(task_id).exists()
        if not task:
            raise not_found(device.env)
        try:
            task.action_claim()
        except UserError as error:
            if task._claimed_by_someone_else():
                raise LaboratoryFileError(ALREADY_CLAIMED, error.args[0]) from error
            raise
        return task._mobile_detail()

    @laboratory_api_route("/tasks/<int:task_id>/start", ["POST"], "startTask", permission=False)
    def start_task(self, device, _body, task_id):
        task = readable_task(device.env, task_id)
        task.action_start()
        return task._mobile_detail()

    @laboratory_api_route("/tasks/<int:task_id>/done", ["POST"], "finishTask", permission=False)
    def finish_task(self, device, _body, task_id):
        task = readable_task(device.env, task_id)
        task.action_done()
        return task._mobile_detail()

    @laboratory_api_route("/tasks/<int:task_id>/assign", ["POST"], "assignTask", permission=False)
    def assign_task(self, device, body, task_id):
        task = readable_task(device.env, task_id)
        task._assign_from_phone(body)
        # A task moved to someone the person no longer sees is not read back.
        if not task._filtered_access("read"):
            return None
        return task._mobile_detail()
