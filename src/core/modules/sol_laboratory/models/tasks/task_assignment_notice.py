from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_MAIL_MESSAGE, MODEL_TASK
from odoo.addons.sol_laboratory.constants.notifications import EVENT_TASK_ASSIGNED

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_task as TaskAssignmentNoticeBase
else:
    TaskAssignmentNoticeBase = object


# Nhiệm Vụ: a person is told when someone else assigns them a task; claiming a task tells nobody.
class TaskAssignmentNotice(models.Model, TaskAssignmentNoticeBase):
    _inherit = MODEL_TASK

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        tasks._notify_assignee()
        return tasks

    def write(self, vals):
        before = {task: task.assignee_id for task in self} if "assignee_id" in vals else {}
        result = super().write(vals)
        self.filtered(lambda task: task in before and task.assignee_id != before[task])._notify_assignee()
        return result

    def _notify_assignee(self):
        """Tell the assignee of each task that another person assigned it to them. Loading data tells nobody."""
        if self.env.su:
            return
        stamp = fields.Datetime.to_string(fields.Datetime.now())
        for task in self.sudo():
            assignee = task.assignee_id
            if not assignee.user_id or not task.assigned_by_id or task.assigned_by_id == assignee:
                continue
            self.env[MODEL_MAIL_MESSAGE].raise_event(
                EVENT_TASK_ASSIGNED,
                task,
                f"task:{task.id}:assigned:{assignee.id}:{stamp}",
                self.env._("%(person)s assigned you %(task)s.", person=task.assigned_by_id.name, task=task.name),
                subject=task.name,
                partners=assignee.user_id.partner_id,
            )
