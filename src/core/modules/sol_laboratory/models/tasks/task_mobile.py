from datetime import UTC, datetime
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import AccessError, MissingError
from odoo.fields import Command, Domain

from odoo.addons.sol_laboratory.constants.laboratory_files import IDEMPOTENCY_CONFLICT, PERMISSION_DENIED
from odoo.addons.sol_laboratory.constants.medilab_mobile import ASSIGNEE_LIMIT
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DEPARTMENT,
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_IDEMPOTENCY_MIXIN,
    MODEL_PERSON,
    MODEL_TASK,
    MODEL_TASK_REASSIGN,
)
from odoo.addons.sol_laboratory.constants.tasks import FINAL_STATUSES
from odoo.addons.sol_laboratory.services.document_code import document_code
from odoo.addons.sol_laboratory.services.laboratory_api import api_datetime
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.mobile_documents import document_screen
from odoo.addons.sol_laboratory.services.model_lookup import dynamic_model

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_task as TaskMobileBase
else:
    TaskMobileBase = object

OPEN_STATUSES = ("assigned", "in_progress")
# The lists of Medilab Mobile's to-do list: their tasks and their order, the same as the web's lists.
TASK_LISTS = {
    "open": (Domain("is_mine", "=", True) & Domain("status", "in", OPEN_STATUSES), "deadline, id"),
    "finished": (Domain("is_mine", "=", True) & Domain("status", "=", "done"), "done_at desc, id desc"),
    "queue": (Domain("in_my_queue", "=", True), "deadline, id"),
}
GENERAL_TASK_TYPE = "sol_laboratory.task_type_general"


# Nhiệm Vụ: what Medilab Mobile reads and does with tasks, with the person's rights; a phone creates a task once per
# Idempotency-Key.
class TaskMobile(models.Model, TaskMobileBase):
    _name = MODEL_TASK
    _inherit = [MODEL_TASK, MODEL_LABORATORY_IDEMPOTENCY_MIXIN]
    _idempotency_device_field = "created_by_device_id"

    if not TYPE_CHECKING:
        # The phone the task was created by hand on; empty for a task created on the web or by the system.
        created_by_device_id = fields.Many2one(MODEL_LABORATORY_DEVICE, readonly=True, copy=False, ondelete="set null")

    _device_idempotency_key_unique = models.UniqueIndex(
        "(created_by_device_id, idempotency_key) WHERE idempotency_key IS NOT NULL",
        "This phone already created a task with this Idempotency-Key.",
    )

    @api.model
    def _mobile_list(self, name, offset, limit):
        """A page of the person's open tasks, finished tasks or queues, in the order the web lists them, and whether
        another page follows."""
        domain, order = TASK_LISTS[name]
        tasks = self.search(domain, order=order, offset=offset, limit=limit + 1)
        return tasks[:limit], len(tasks) > limit

    @api.model
    def _mobile_day(self):
        """The person's day, as the Tasks app opens on it."""
        day = self.get_dashboard_data()
        return {
            "person": day["person"],
            "day_start": api_datetime(fields.Datetime.to_datetime(day["day_start"])),
            "day_end": api_datetime(fields.Datetime.to_datetime(day["day_end"])),
            "open_count": day["open_count"],
            "overdue_count": day["overdue_count"],
            "due_today_count": day["due_today_count"],
            "finished_count": day["finished_count"],
            "finished_week_count": day["finished_week_count"],
            "claimable_count": day["claimable_count"],
            **{
                name: self.browse([task["id"] for task in day[name]])._mobile_values()
                for name in ("next_up", "planned_today", "claimable")
            },
        }

    def _mobile_values(self):
        """The tasks as Medilab Mobile lists them. The department's and the assignee's names are read with full
        rights, as the web's dashboard reads them."""
        documents = self._mobile_documents()
        return [
            {
                "id": task.id,
                "name": task.name,
                "type": task.type_id.name,
                "status": task.status,
                "action": task.action or "",
                "deadline": api_datetime(task.deadline),
                "planned_start": api_datetime(task.planned_start),
                "planned_end": api_datetime(task.planned_end),
                "done_at": api_datetime(task.done_at),
                "department": task.sudo().department_id.display_name or "",
                "assignee": task.sudo().assignee_id.name or "",
                "location": task.sampling_location_id.display_name or "",
                "closed_by_system": task.closed_by_system,
                "document": documents.get(task.id),
            }
            for task in self
        ]

    def _mobile_documents(self):
        """The document each task opens, by task id, with its code and the app's screen for it, looked up once per
        model; the app reads a document with the person's rights when they open it."""
        documents = {}
        by_model = {}
        for task in self:
            if task.document_model and task.document_id and task.document_model in self.env:
                by_model.setdefault(task.document_model, []).append(task)
        for model, tasks in by_model.items():
            records = dynamic_model(self.env, model)
            existing = records.browse([task.document_id for task in tasks]).exists()
            screen = document_screen(records)
            for task in tasks:
                record = existing.filtered(lambda row, document_id=task.document_id: row.id == document_id)
                if record:
                    documents[task.id] = {
                        "model": model,
                        "id": record.id,
                        "code": document_code(record),
                        "screen": screen,
                    }
        return documents

    def _mobile_detail(self):
        """The task with its note, its method's steps and the actions the person may take on it, as the web's form
        shows them."""
        self.ensure_one()
        task = self
        return {
            **task._mobile_values()[0],
            "note": task.note or "",
            "reassign_reason": task.reassign_reason or "",
            "assigned_by": task.sudo().assigned_by_id.name or "",
            "steps": [
                {
                    "minutes": step.duration_minutes,
                    "instruction": step.instruction or "",
                    "note": step.note or "",
                    "location": step.location_id.display_name or "",
                }
                for step in task.method_step_ids.sorted("sequence")
            ],
            "actions": task._mobile_actions(),
        }

    def _mobile_actions(self):
        """The actions the web's form shows the person on the task."""
        self.ensure_one()
        open_and_mine = self.is_mine and self.status in OPEN_STATUSES
        return {
            "claim": self.in_my_queue,
            "start": self.is_mine and self.status == "assigned",
            "done": open_and_mine and not self.closed_by_system,
            "assign": self._may_assign() and self.can_edit and self.status not in FINAL_STATUSES,
        }

    @api.model
    def _may_assign(self):
        return self._has_permission("edit")

    @api.model
    def _may_create(self):
        return self._has_permission("create")

    @api.model
    def _create_from_phone(self, device, values, key=None):
        """The task the person creates by hand on the phone: of the general type, opening no document, in the
        assignee's department. A request repeated with its Idempotency-Key gets the task it created."""
        assignee = self.env[MODEL_PERSON].browse(values["assignee_id"]).exists()
        if not assignee:
            raise MissingError(self.env._("Nothing is found at this address."))
        task_values = {
            "type_id": self.env.ref(GENERAL_TASK_TYPE).id,
            "name": values["name"],
            "note": values.get("note") or False,
            "assignee_id": assignee.id,
            "department_id": assignee.sudo().department_id.id or False,
            "deadline": utc_datetime(values["deadline"]),
        }
        created = self._created_with_key(device, key)
        if created:
            if (created.name, created.note or False, created.assignee_id.id, created.deadline) != (
                task_values["name"],
                task_values["note"],
                task_values["assignee_id"],
                task_values["deadline"],
            ):
                raise LaboratoryFileError(
                    IDEMPOTENCY_CONFLICT, self.env._("This Idempotency-Key was already sent with another request.")
                )
            return created
        if not self._may_create():
            raise LaboratoryFileError(PERMISSION_DENIED, self.env._("You may not create tasks."))
        try:
            return self._create_once(device, key, task_values)
        except AccessError as error:
            raise LaboratoryFileError(PERMISSION_DENIED, error.args[0]) from error

    def _assign_from_phone(self, values):
        """Assign or reassign the task through the web's assign wizard, so its checks apply: to the person, to the
        department, or to the person in their department, with the reason the task asks for when it moves away. A
        person outside the task's department takes the task to theirs."""
        self.ensure_one()
        if not self._may_assign() or not self.can_edit:
            raise LaboratoryFileError(PERMISSION_DENIED, self.env._("You may not assign %s.", self.name))
        assignee = self.env[MODEL_PERSON]
        if values.get("assignee_id"):
            assignee = assignee.browse(values["assignee_id"]).exists()
            if not assignee:
                raise MissingError(self.env._("Nothing is found at this address."))
        if "department_id" in values:
            department = self.env[MODEL_DEPARTMENT].browse(values["department_id"] or []).exists()
            if values["department_id"] and not department:
                raise MissingError(self.env._("Nothing is found at this address."))
        elif assignee and self.department_id and assignee.sudo().department_id != self.department_id:
            department = assignee.sudo().department_id
        else:
            department = self.department_id
        wizard = self.env[MODEL_TASK_REASSIGN].create(
            {
                "task_ids": [Command.set(self.ids)],
                "department_id": department.id,
                "assignee_id": assignee.id,
                "reason": values.get("reason") or False,
            }
        )
        try:
            wizard.action_confirm()
        except AccessError as error:
            raise LaboratoryFileError(PERMISSION_DENIED, error.args[0]) from error

    @api.model
    def _mobile_assignees(self, query):
        """The active people with a login and the departments whose name has the query, whom the person may give a
        task to."""
        if not self._may_assign() and not self._may_create():
            raise LaboratoryFileError(PERMISSION_DENIED, self.env._("You may not assign tasks."))
        query = (query or "").strip()
        # The people the person may read, among them those with a login, which only full rights read.
        readable = self.env[MODEL_PERSON]._search([("name", "ilike", query)])
        people = (
            self.env[MODEL_PERSON]
            .sudo()
            .search([("id", "in", readable), ("user_id", "!=", False)], order="name", limit=ASSIGNEE_LIMIT)
        )
        departments = self.env[MODEL_DEPARTMENT].search(
            [("parent_id", "=", False), ("name", "ilike", query)], order="name", limit=ASSIGNEE_LIMIT
        )
        return {
            "people": [
                {"id": person.id, "name": person.name, "department": person.sudo().department_id.name or ""}
                for person in people
            ],
            "departments": [{"id": department.id, "name": department.name} for department in departments],
        }


def utc_datetime(value):
    """The date and time of the API as Odoo stores it, in UTC without a zone; one without a zone is in UTC."""
    moment = datetime.fromisoformat(value)
    if moment.tzinfo:
        moment = moment.astimezone(UTC).replace(tzinfo=None)
    return moment.replace(microsecond=0)
