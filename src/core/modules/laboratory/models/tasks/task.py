from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain

from odoo.addons.laboratory.constants.models import (
    MODEL_DEPARTMENT,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_TASK,
    MODEL_TASK_TYPE,
)
from odoo.addons.laboratory.constants.tasks import FINAL_STATUSES, MANUAL_TRIGGER

TASK_ACTION_CONTEXT = "medilab_task_action"
OPEN_STATUSES = ("assigned", "in_progress")
NEXT_UP_LIMIT = 6
NOT_IN = "not in"
CLAIMABLE_LIMIT = 3


# Nhiệm Vụ
class Task(models.Model):
    _name = MODEL_TASK
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Task"
    _order = "deadline, id"
    _permission_actions = ("read", "create", "edit", "delete")

    # The kind of task.
    type_id = fields.Many2one(MODEL_TASK_TYPE, string="Type", required=True, ondelete="restrict", index=True)
    # Short description of the work, such as "Test lead on sample PTN-0042".
    name = fields.Char(required=True)
    # Details of the work.
    note = fields.Text()
    # Technical name of the document the task opens.
    document_model = fields.Char(string="Document Type")
    # Id of the document the task opens.
    document_id = fields.Many2oneReference(model_field="document_model", string="Document")
    # Action the task opens on the document, such as enter_result or sign.
    action = fields.Char()
    # Department whose queue holds the task until someone is assigned.
    department_id = fields.Many2one(MODEL_DEPARTMENT, ondelete="restrict")
    # Person who does the task; empty while it waits in a queue.
    assignee_id = fields.Many2one(MODEL_PERSON, string="Assignee", ondelete="restrict")
    # Person who assigned the task; the assignee themselves when they claimed it.
    assigned_by_id = fields.Many2one(MODEL_PERSON, string="Assigned By", ondelete="restrict", readonly=True)
    # Why the task was last moved to another person or department.
    reassign_reason = fields.Text(readonly=True)
    # When the task must be done.
    deadline = fields.Datetime(index=True)
    # Planned start on the assignee's schedule.
    planned_start = fields.Datetime()
    # Planned end on the assignee's schedule.
    planned_end = fields.Datetime()
    # Open, assigned, in progress, done or cancelled.
    status = fields.Selection(
        [
            ("open", "Open"),
            ("assigned", "Assigned"),
            ("in_progress", "In progress"),
            ("done", "Done"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="open",
        readonly=True,
    )
    # When the task was done.
    done_at = fields.Datetime(readonly=True)
    # True when the system closes the task once its work is done, rather than the assignee.
    closed_by_system = fields.Boolean(compute="_compute_closed_by_system")
    # True when the current user is the assignee.
    is_mine = fields.Boolean(compute="_compute_is_mine", search="_search_is_mine")
    # True when the task waits in a queue the current user can claim from.
    in_my_queue = fields.Boolean(compute="_compute_in_my_queue", search="_search_in_my_queue")

    _assignee_status_idx = models.Index("(assignee_id, status)")
    _department_status_idx = models.Index("(department_id, status)")
    _document_idx = models.Index("(document_model, document_id)")
    _planned_period = models.Constraint(
        "CHECK(planned_end IS NULL OR planned_start IS NULL OR planned_end >= planned_start)",
        "A task cannot end before it starts.",
    )

    @api.depends("type_id.trigger")
    def _compute_closed_by_system(self):
        for task in self:
            task.closed_by_system = task.type_id.trigger != MANUAL_TRIGGER

    def _compute_is_mine(self):
        person = self.env[MODEL_PERSON]._current()
        for task in self:
            task.is_mine = bool(person) and task.assignee_id == person

    def _search_is_mine(self, operator, value):
        if operator != "in" or True not in value:
            return NotImplemented
        person = self.env[MODEL_PERSON]._current()
        return Domain("assignee_id", "=", person.id) if person else Domain.FALSE

    def _compute_in_my_queue(self):
        person = self.env[MODEL_PERSON]._current()
        for task in self:
            task.in_my_queue = task.status == "open" and task.sudo()._claimable_by(person)

    def _search_in_my_queue(self, operator, value):
        if operator != "in" or True not in value:
            return NotImplemented
        person = self.env[MODEL_PERSON]._current()
        if not person:
            return Domain.FALSE
        department_queue = (
            Domain("department_id", "=", person.department_id.id) if person.department_id else Domain.FALSE
        )
        role_queue = (
            Domain("department_id", "=", False)
            & Domain("type_id.route", "=", "role")
            & Domain("type_id.role_id", "in", person.role_ids.ids)
        )
        return Domain("status", "=", "open") & (department_queue | role_queue)

    @api.constrains("status", "assignee_id", "department_id", "type_id")
    def _check_queue(self):
        for task in self:
            if task.status != "open" or task.assignee_id or task.department_id or task.type_id.route == "role":
                continue
            raise ValidationError(self.env._("%s needs an assignee or a department whose queue holds it.", task.name))

    @api.model_create_multi
    def create(self, vals_list):
        task_types = self.env[MODEL_TASK_TYPE]
        person = self.env[MODEL_PERSON]._current()
        for vals in vals_list:
            task_type = task_types.browse(vals.get("type_id"))
            if not self.env.su:
                self._check_created_by_hand(task_type, vals)
            vals.setdefault("document_model", task_type.document_model)
            vals.setdefault("action", task_type.action)
            if not vals.get("deadline") and task_type.deadline_hours:
                vals["deadline"] = fields.Datetime.now() + timedelta(hours=task_type.deadline_hours)
            if vals.get("assignee_id"):
                vals.setdefault("status", "assigned")
                if not self.env.su:
                    vals.setdefault("assigned_by_id", person.id)
        return super().create(vals_list)

    def write(self, vals):
        if {"assignee_id", "department_id"} & set(vals):
            self._check_reassign(vals)
        return super().write(vals)

    def _check_created_by_hand(self, task_type, vals):
        if task_type.trigger != MANUAL_TRIGGER:
            raise UserError(self.env._("Tasks of %s are created by the system.", task_type.name))
        if not vals.get("assignee_id") or not vals.get("deadline"):
            raise UserError(self.env._("A task created by hand needs an assignee and a deadline."))
        assignee = self.env[MODEL_PERSON].browse(vals["assignee_id"]).sudo()
        if vals.get("department_id") and assignee.department_id.id != vals["department_id"]:
            raise UserError(self.env._("%s is not in the task's department.", assignee.name))

    def _check_reassign(self, vals):
        for task in self:
            if task.status in FINAL_STATUSES:
                raise UserError(self.env._("%s is finished and cannot be assigned again.", task.name))
            moves_person = task.assignee_id and vals.get("assignee_id", task.assignee_id.id) != task.assignee_id.id
            moves_department = vals.get("department_id", task.department_id.id) != task.department_id.id
            if (moves_person or moves_department) and not vals.get("reassign_reason"):
                raise UserError(self.env._("Give a reason for moving %s to another person or department.", task.name))

    def _claimable_by(self, person):
        self.ensure_one()
        if not person:
            return False
        if self.department_id:
            return self.department_id == person.department_id
        return self.type_id.route == "role" and self.type_id.role_id in person.role_ids

    def action_claim(self):
        person = self.env[MODEL_PERSON]._current()
        tasks = self.sudo()
        locked = tasks.try_lock_for_update()
        for task in tasks:
            if task not in locked or task.assignee_id or task.status != "open":
                raise UserError(self.env._("%s is already claimed.", task.name))
            if not task._claimable_by(person):
                raise UserError(self.env._("%s waits in a queue you do not belong to.", task.name))
        tasks.write({"assignee_id": person.id, "assigned_by_id": person.id, "status": "assigned"})

    def action_start(self):
        tasks = self._own_tasks()
        if any(task.status != "assigned" for task in tasks):
            raise UserError(self.env._("Only an assigned task can be started."))
        tasks.write({"status": "in_progress"})

    def action_done(self):
        tasks = self._own_tasks()
        for task in tasks:
            if task.closed_by_system:
                raise UserError(self.env._("%s is done by the system once its work is done.", task.name))
            if task.status not in ("assigned", "in_progress"):
                raise UserError(self.env._("%s is not open.", task.name))
        tasks.write({"status": "done", "done_at": fields.Datetime.now()})

    def action_cancel(self):
        for task in self:
            if task.closed_by_system:
                raise UserError(self.env._("%s is cancelled by the system when its work is cancelled.", task.name))
            if task.status in FINAL_STATUSES:
                raise UserError(self.env._("%s is already finished.", task.name))
        self.write({"status": "cancelled"})

    def action_open_document(self):
        self.ensure_one()
        if not self.document_model or not self.document_id or self.document_model not in self.env:
            return self._get_records_action()
        document = self.env[self.document_model].browse(self.document_id)
        if hasattr(document, "_get_task_action"):
            return document._get_task_action(self.action)
        return document._get_records_action(context={TASK_ACTION_CONTEXT: self.action})

    def _own_tasks(self):
        person = self.env[MODEL_PERSON]._current()
        others = self.filtered(lambda task: not person or task.assignee_id != person)
        if others:
            raise UserError(self.env._("Only the assignee of %s can do this.", others[0].name))
        return self.sudo()

    @api.model
    def _create_for_event(self, trigger, document=None, **values):
        """Create a task of each task type the trigger creates.

        Features call this when their event happens. values may give department, assignee, deadline, planned_start,
        planned_end, name and note; department and assignee are records, used when the type's route asks for them.
        Returns the tasks created.
        """
        department = values.pop("department", None)
        assignee = values.pop("assignee", None)
        task_types = self.env[MODEL_TASK_TYPE].sudo().search([("trigger", "=", trigger)])
        vals_list = [
            {
                "type_id": task_type.id,
                "name": task_type.name if not document else f"{task_type.name}: {document.display_name}",
                "document_model": document._name if document else task_type.document_model,
                "document_id": document.id if document else False,
                "department_id": department.id if department and task_type.route == "department" else False,
                "assignee_id": assignee.id if assignee and task_type.route == "person" else False,
                **values,
            }
            for task_type in task_types
        ]
        return self.sudo().create(vals_list)

    @api.model
    def _close_for_document(self, document, action=None):
        """Mark done the tasks the system created for the document, or only those of one action."""
        self._system_tasks_of(document, action).write({"status": "done", "done_at": fields.Datetime.now()})

    @api.model
    def _cancel_for_document(self, document, action=None):
        """Cancel the tasks the system created for the document, when its work is cancelled."""
        self._system_tasks_of(document, action).write({"status": "cancelled"})

    @api.model
    def _system_tasks_of(self, document, action):
        domain = (
            Domain("document_model", "=", document._name)
            & Domain("document_id", "in", document.ids)
            & Domain("status", NOT_IN, FINAL_STATUSES)
            & Domain("type_id.trigger", "!=", MANUAL_TRIGGER)
        )
        if action:
            domain &= Domain("action", "=", action)
        return self.sudo().search(domain)

    def _in_use_domain(self):
        return Domain("status", NOT_IN, FINAL_STATUSES)

    @api.model
    def get_dashboard_data(self):
        """The current person's day: open tasks, today's plan, finished work and the tasks they can claim."""
        now = fields.Datetime.now()
        day_start, day_end = self._today_bounds()
        mine = Domain("is_mine", "=", True)
        open_tasks = self.search(mine & Domain("status", "in", OPEN_STATUSES))
        overdue = open_tasks.filtered(lambda task: task.deadline and task.deadline < now)
        planned_today = self.search(
            mine
            & Domain("status", "!=", "cancelled")
            & Domain("planned_start", "<", day_end)
            & Domain("planned_end", ">", day_start),
            order="planned_start",
        )
        finished = mine & Domain("status", "=", "done")
        claimable = Domain("in_my_queue", "=", True)
        return {
            "person": self.env[MODEL_PERSON]._current().name or self.env.user.name,
            "day_start": fields.Datetime.to_string(day_start),
            "day_end": fields.Datetime.to_string(day_end),
            "open_count": len(open_tasks),
            "overdue_count": len(overdue),
            "due_today_count": len(open_tasks.filtered(lambda t: t.deadline and day_start <= t.deadline < day_end)),
            "next_up": (overdue + (open_tasks - overdue))[:NEXT_UP_LIMIT]._dashboard_values(),
            "planned_today": planned_today._dashboard_values(),
            "finished_count": self.search_count(finished),
            "finished_week_count": self.search_count(finished & Domain("done_at", ">=", day_start - timedelta(days=6))),
            "claimable_count": self.search_count(claimable),
            "claimable": self.search(claimable, limit=CLAIMABLE_LIMIT)._dashboard_values(),
            "unfinished_count": self.search_count(Domain("status", NOT_IN, FINAL_STATUSES)),
        }

    @api.model
    def _today_bounds(self):
        tz_name = self.env.user.tz or "UTC"
        today = fields.Date.context_today(self.with_context(tz=tz_name))
        start = datetime.combine(today, time.min, tzinfo=ZoneInfo(tz_name)).astimezone(UTC).replace(tzinfo=None)
        return start, start + timedelta(days=1)

    def _dashboard_values(self):
        return [
            {
                "id": task.id,
                "name": task.name,
                "status": task.status,
                "deadline": fields.Datetime.to_string(task.deadline),
                "planned_start": fields.Datetime.to_string(task.planned_start),
                "planned_end": fields.Datetime.to_string(task.planned_end),
                "closed_by_system": task.closed_by_system,
                "has_document": bool(task.document_id),
                "department": task.sudo().department_id.display_name or "",
            }
            for task in self
        ]
