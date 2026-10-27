from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain

from odoo.addons.sol_laboratory.constants.departments import DEPARTMENT_DOMAIN
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_DEPARTMENT,
    MODEL_LOCATION,
    MODEL_LOCK_MIXIN,
    MODEL_MACHINE_BOOKING,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_SAMPLE_TEST,
    MODEL_TASK,
    MODEL_TASK_TYPE,
    MODEL_TESTING_METHOD_STEP,
)
from odoo.addons.sol_laboratory.constants.tasks import FINAL_STATUSES, MANUAL_TRIGGER, TESTING_ACTION

TASK_ACTION_CONTEXT = "medilab_task_action"
OPEN_STATUSES = ("assigned", "in_progress")
NEXT_UP_LIMIT = 6
NOT_IN = "not in"
CLAIMABLE_LIMIT = 3
# Fields that say what a task is and which document it opens; only the system sets them.
DOCUMENT_LINK_FIELDS = {"type_id", "document_model", "document_id", "action"}
LINKED_BY_SYSTEM = "linked_by_system"


# Nhiệm Vụ
class Task(models.Model):
    _name = MODEL_TASK
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
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
    # True when the system created the task with its type and document and nobody changed them since; only such tasks
    # act on their document with full rights.
    linked_by_system = fields.Boolean(readonly=True, copy=False)
    # Department whose queue holds the task until someone is assigned.
    department_id = fields.Many2one(MODEL_DEPARTMENT, ondelete="restrict", domain=DEPARTMENT_DOMAIN)
    # Person who does the task; empty while it waits in a queue.
    assignee_id = fields.Many2one(MODEL_PERSON, string="Assignee", ondelete="restrict")
    # Person who assigned the task; the assignee themselves when they claimed it.
    assigned_by_id = fields.Many2one(MODEL_PERSON, string="Assigned By", ondelete="restrict", readonly=True)
    # Why the task was last moved to another person or department.
    reassign_reason = fields.Text(readonly=True)
    # People who moved the task to another department; they still read it, but no longer change it.
    moved_out_by_ids = fields.Many2many(
        MODEL_PERSON, "medilab_task_moved_out_by_rel", "task_id", "person_id", readonly=True, copy=False
    )
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
    # Machine bookings made for the task.
    booking_ids = fields.One2many(MODEL_MACHINE_BOOKING, "task_id", string="Bookings")
    # Steps of the testing method of a testing task's sample test; empty for any other task.
    method_step_ids = fields.Many2many(
        MODEL_TESTING_METHOD_STEP, compute="_compute_sample_test_details", string="Method Steps"
    )
    # The location a testing task's sample was taken from; empty for any other task.
    sampling_location_id = fields.Many2one(
        MODEL_LOCATION, compute="_compute_sample_test_details", string="Sampling Location"
    )
    # True when the system closes the task once its work is done, rather than the assignee.
    closed_by_system = fields.Boolean(compute="_compute_closed_by_system")
    # True when the current user is the assignee.
    is_mine = fields.Boolean(compute="_compute_is_mine", search="_search_is_mine")
    # True when the task waits in a queue the current user can claim from.
    in_my_queue = fields.Boolean(compute="_compute_in_my_queue", search="_search_in_my_queue")
    # True when the current user may change the task; one who moved it to another department only reads it.
    can_edit = fields.Boolean(compute="_compute_can_edit")

    _assignee_status_idx = models.Index("(assignee_id, status)")
    _department_status_idx = models.Index("(department_id, status)")
    _document_idx = models.Index("(document_model, document_id)")
    _planned_period = models.Constraint(
        "CHECK(planned_end IS NULL OR planned_start IS NULL OR planned_end >= planned_start)",
        "A task cannot end before it starts.",
    )

    @api.depends("document_model", "document_id", "action", "type_id", "linked_by_system")
    def _compute_sample_test_details(self):
        # A person reads the tasks assigned to them or queued for their department without reading the sample
        # test, so only the hops to its method and its sample's location run as superuser; steps and locations are
        # master data every internal user reads, and nothing else of the test is returned.
        testing = self.filtered_domain(self._testing_domain())
        tests = self.env[MODEL_SAMPLE_TEST].sudo().browse(testing.mapped("document_id")).exists()
        steps_by_test = {test.id: test.parameter_method_id.method_id.step_ids.ids for test in tests}
        location_by_test = {test.id: test.sample_id.sampling_location_id.id for test in tests}
        steps = self.env[MODEL_TESTING_METHOD_STEP]
        locations = self.env[MODEL_LOCATION]
        for task in self:
            test_id = task.document_id if task in testing else 0
            task.method_step_ids = steps.browse(steps_by_test.get(test_id, []))
            task.sampling_location_id = locations.browse(location_by_test.get(test_id))

    @api.model
    def _testing_domain(self):
        """Testing tasks the system opened on sample tests: only these reach their test as superuser. A task made by
        hand never counts, whatever document it names, nor does one whose type or document changed after it was
        created or that predates linked_by_system and was not verified."""
        return (
            Domain("document_model", "=", MODEL_SAMPLE_TEST)
            & Domain("action", "=", TESTING_ACTION)
            & Domain("document_id", "!=", False)
            & Domain("type_id.trigger", "!=", MANUAL_TRIGGER)
            & Domain("type_id.document_model", "=", MODEL_SAMPLE_TEST)
            & Domain("type_id.action", "=", TESTING_ACTION)
            & Domain(LINKED_BY_SYSTEM, "=", True)
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

    @api.depends_context("uid")
    def _compute_can_edit(self):
        editable = self.filtered("id")._filtered_access("write")
        for task in self:
            task.can_edit = not task.id or task in editable

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
            else:
                vals.setdefault(LINKED_BY_SYSTEM, True)
            vals.setdefault("document_model", task_type.document_model)
            vals.setdefault("action", task_type.action)
            if not vals.get("deadline") and task_type.deadline_hours:
                vals["deadline"] = fields.Datetime.now() + timedelta(hours=task_type.deadline_hours)
            if vals.get("assignee_id"):
                vals.setdefault("status", "assigned")
                if not self.env.su:
                    vals.setdefault("assigned_by_id", person.id)
        tasks = super().create(vals_list)
        tasks._sync_calendar_event()
        return tasks

    def write(self, vals):
        if not self.env.su and (DOCUMENT_LINK_FIELDS | {LINKED_BY_SYSTEM}) & set(vals):
            raise UserError(self.env._("The type of a task and the document it opens cannot change."))
        if DOCUMENT_LINK_FIELDS & set(vals):
            # A task whose type or document changes is no longer the one the system linked, whatever the call says;
            # only a separate confirmation trusts it again.
            vals = {**vals, LINKED_BY_SYSTEM: False}
        if {"assignee_id", "department_id"} & set(vals):
            self._check_reassign(vals)
        moved_out = self.filtered(
            lambda task: vals.get("department_id", task.department_id.id) != task.department_id.id
        )
        result = super().write(vals)
        person = self.env[MODEL_PERSON]._current()
        if moved_out and person:
            # Full rights: the person no longer changes a task that waits in another department's queue.
            moved_out.sudo().moved_out_by_ids = [Command.link(person.id)]
        if "assignee_id" in vals:
            self.env[MODEL_SAMPLE_TEST]._follow_assignment(self)
            self.env[MODEL_MACHINE_BOOKING]._follow_assignment(self)
        if not self.env.context.get("medilab_skip_calendar_sync") and {
            "planned_start",
            "planned_end",
            "assignee_id",
            "name",
            "status",
        } & set(vals):
            self._sync_calendar_event()
        return result

    def _check_created_by_hand(self, task_type, vals):
        if task_type.trigger != MANUAL_TRIGGER:
            raise UserError(self.env._("Tasks of %s are created by the system.", task_type.name))
        if not vals.get("assignee_id") or not vals.get("deadline"):
            raise UserError(self.env._("A task created by hand needs an assignee and a deadline."))
        # Only the system links a document, so a task never opens a document its creator could not.
        if (
            vals.get("document_id")
            or vals.get(LINKED_BY_SYSTEM)
            or any(vals.get(name) not in (None, False, task_type[name]) for name in ("document_model", "action"))
        ):
            raise UserError(self.env._("A task created by hand opens no document."))
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

    def _sync_calendar_event(self):
        """Keep one calendar event on a planned task. The event has no alarm, so Odoo does not also remind."""
        if self.env.context.get("medilab_skip_calendar_sync"):
            return
        events = self.env["calendar.event"].sudo()
        for task in self:
            event = events.search([("medilab_task_id", "=", task.id)], limit=1)
            user = task.assignee_id.sudo().user_id
            # A testing task planned by its bookings shows on the calendar through the bookings' events.
            planned_by_bookings = task.sudo().booking_ids.calendar_event_id
            if task.status in FINAL_STATUSES or not task.planned_start or not user or planned_by_bookings:
                if event:
                    event.with_context(medilab_skip_calendar_sync=True).unlink()
                continue
            stop = task.planned_end or task.planned_start + timedelta(hours=1)
            values = {
                "name": task.name,
                "start": task.planned_start,
                "stop": stop,
                "user_id": user.id,
                "partner_ids": [Command.set([user.partner_id.id])],
                "alarm_ids": [Command.clear()],
                "location": task.sampling_location_id.display_name or False,
            }
            if event:
                event.with_context(medilab_skip_calendar_sync=True).write(values)
            else:
                events.with_context(medilab_skip_calendar_sync=True).create({**values, "medilab_task_id": task.id})

    def action_assign_sample(self):
        """Open the assign wizard on every unfinished testing task of the task's sample in its department."""
        self.ensure_one()
        testing = self._testing_domain()
        sample = self.env[MODEL_SAMPLE_TEST].sudo().browse(self.filtered_domain(testing).document_id).sample_id
        tasks = self.search(
            testing
            & Domain("document_id", "in", sample.test_ids.ids)
            & Domain("department_id", "=", self.department_id.id)
            & Domain("status", NOT_IN, FINAL_STATUSES)
        )
        action = self.env["ir.actions.actions"]._for_xml_id("sol_laboratory.action_medilab_task_reassign")
        action["context"] = {"active_ids": (tasks or self).ids}
        return action

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
            & Domain(LINKED_BY_SYSTEM, "=", True)
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
                "location": task.sampling_location_id.display_name or "",
            }
            for task in self
        ]
