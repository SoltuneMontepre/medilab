from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.departments import DEPARTMENT_DOMAIN
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DEPARTMENT,
    MODEL_PARAMETER_AUTHORIZATION,
    MODEL_PERSON,
    MODEL_TASK,
    MODEL_TASK_REASSIGN,
    MODEL_TEST_PARAMETER,
)
from odoo.addons.sol_laboratory.services.record_id import persisted_ids

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_task_reassign as TaskReassignBase
else:
    TaskReassignBase = object


# Assigns tasks to a person or moves them to another department's queue, with the reason for a move.
class TaskReassign(models.TransientModel, TaskReassignBase):
    _name = MODEL_TASK_REASSIGN
    _description = "Assign Tasks"

    if not TYPE_CHECKING:
        # The tasks to assign or move.
        task_ids = fields.Many2many(MODEL_TASK, string="Tasks", required=True)
        # Department whose queue holds the tasks.
        department_id = fields.Many2one(MODEL_DEPARTMENT, domain=DEPARTMENT_DOMAIN)
        # True when a task is a testing task, so the tasks stay in the department of its way of testing.
        department_fixed = fields.Boolean(compute="_compute_fixed_department")
        # The department of the way of testing of every testing task among the tasks; empty when they differ.
        fixed_department_id = fields.Many2one(MODEL_DEPARTMENT, compute="_compute_fixed_department")
        # Person who does the tasks; empty to leave them in the department's queue.
        assignee_id = fields.Many2one(MODEL_PERSON, string="Assignee")
        # Why the tasks move to another person or department.
        reason = fields.Text()
        # True when a task moves away from its person or department, so a reason is needed.
        reason_required = fields.Boolean(compute="_compute_reason_required")
        # True when a task is a testing task, so only people authorized to test its parameter are offered.
        authorization_required = fields.Boolean(compute="_compute_authorized_person_ids")
        # People authorized to test the parameters of every testing task among the tasks.
        authorized_person_ids = fields.Many2many(MODEL_PERSON, compute="_compute_authorized_person_ids")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        tasks = self.env[MODEL_TASK].browse(self.env.context.get("active_ids", []))
        values["task_ids"] = [fields.Command.set(persisted_ids(tasks))]
        way_departments = tasks._way_departments()
        if way_departments:
            values["department_id"] = way_departments.id if len(way_departments) == 1 else False
        elif len(tasks.department_id) == 1:
            values["department_id"] = tasks.department_id.id
        if len(tasks.assignee_id) == 1 and all(tasks.mapped("assignee_id")):
            values["assignee_id"] = tasks.assignee_id.id
        return values

    @api.depends("task_ids", "department_id", "assignee_id")
    def _compute_reason_required(self):
        for wizard in self:
            wizard.reason_required = any(
                task.department_id != wizard.department_id
                or (task.assignee_id and task.assignee_id != wizard.assignee_id)
                for task in wizard.task_ids
            )

    @api.depends("task_ids")
    def _compute_authorized_person_ids(self):
        authorizations = self.env[MODEL_PARAMETER_AUTHORIZATION].sudo()
        # As superuser: the people offered are read by the dialog's domain, not shown.
        for wizard in self.sudo():
            parameters = self.env[MODEL_TEST_PARAMETER].union(task._parameter() for task in wizard.task_ids)
            wizard.authorization_required = bool(parameters)
            candidates = authorizations.search([("parameter_id", "in", parameters.ids)]).person_id
            wizard.authorized_person_ids = candidates.filtered(
                lambda person, parameters=parameters: authorizations._authorized(person, parameters)
            )

    @api.depends("task_ids")
    def _compute_fixed_department(self):
        for wizard in self:
            departments = wizard.task_ids._way_departments()
            wizard.department_fixed = bool(departments)
            wizard.fixed_department_id = departments if len(departments) == 1 else False

    @api.onchange("department_id")
    def _onchange_department_id(self):
        if self.assignee_id and self.department_id and self.assignee_id.department_id != self.department_id:
            self.assignee_id = False

    def _check_fixed_department(self):
        if not self.department_fixed:
            return
        if not self.fixed_department_id:
            raise ValidationError(self.env._("Assign testing tasks of different departments separately."))
        if self.department_id != self.fixed_department_id:
            raise ValidationError(
                self.env._(
                    "These testing tasks stay in %s, which tests them.",
                    self.fixed_department_id.name,
                )
            )

    def action_confirm(self):
        self.ensure_one()
        self._check_fixed_department()
        if self.assignee_id and self.department_id and self.assignee_id.department_id != self.department_id:
            raise ValidationError(
                self.env._(
                    "%(person)s is not in %(department)s.",
                    person=self.assignee_id.name,
                    department=self.department_id.name,
                )
            )
        vals = {
            "department_id": self.department_id.id,
            "assignee_id": self.assignee_id.id,
            "assigned_by_id": self.env[MODEL_PERSON]._current().id if self.assignee_id else False,
            "status": "assigned" if self.assignee_id else "open",
        }
        if self.reason_required:
            vals["reassign_reason"] = self.reason
        self.task_ids.filtered(
            lambda task: task.assignee_id != self.assignee_id or task.department_id != self.department_id
        ).write(vals)
        holder = self.assignee_id.name or self.department_id.name or ""
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._("%(count)s tasks go to %(holder)s.", count=len(self.task_ids), holder=holder),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
