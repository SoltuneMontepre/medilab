from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.laboratory.constants.models import MODEL_PERMISSION_MIXIN, MODEL_ROLE, MODEL_TASK, MODEL_TASK_TYPE
from odoo.addons.laboratory.constants.tasks import MANUAL_TRIGGER

EDITABLE_FIELDS = {"route", "role_id", "deadline_hours"}


# Loại Nhiệm Vụ
class TaskType(models.Model):
    _name = MODEL_TASK_TYPE
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Task Type"
    _order = "name"
    _rec_names_search = ("name", "code")
    _permission_actions = ("edit",)

    # Unique code of the task type.
    code = fields.Char(required=True, readonly=True, copy=False)
    # Task type name in each language.
    name = fields.Char(required=True, readonly=True, translate=True)
    # Event that creates its tasks, such as sample_received; manual for tasks people create.
    trigger = fields.Char(required=True, readonly=True, default=MANUAL_TRIGGER)
    # Technical name of the document its tasks open, such as medilab.sample.test.
    document_model = fields.Char(string="Document Type", readonly=True)
    # Action its tasks open on the document, such as enter_result or sign.
    action = fields.Char(readonly=True)
    # Where a new task goes: the department that does the work, the holders of a role, or a person.
    route = fields.Selection(
        [("department", "Department queue"), ("role", "Holders of a role"), ("person", "A person")],
        required=True,
        default="department",
    )
    # The role whose holders receive the task when the route is role.
    role_id = fields.Many2one(MODEL_ROLE, ondelete="restrict", index="btree_not_null")
    # Hours from creation to the deadline, when the document gives no due date.
    deadline_hours = fields.Integer(string="Default Deadline (Hours)")
    # Tasks of this type.
    task_ids = fields.One2many(MODEL_TASK, "type_id", string="Tasks")

    _code_unique = models.Constraint("UNIQUE(code)", "A task type with this code already exists.")
    _deadline_hours_positive = models.Constraint(
        "CHECK(deadline_hours IS NULL OR deadline_hours >= 0)", "The default deadline cannot be negative."
    )

    @api.constrains("route", "role_id")
    def _check_route_role(self):
        for task_type in self:
            if task_type.route == "role" and not task_type.role_id:
                raise ValidationError(self.env._("Choose the role whose holders receive tasks of %s.", task_type.name))
            if task_type.route != "role" and task_type.role_id:
                raise ValidationError(self.env._("Only a task type routed to a role names a role."))

    def write(self, vals):
        if not self.env.su and set(vals) - EDITABLE_FIELDS:
            raise UserError(
                self.env._("Task types come with the modules; only their route, role and default deadline can change.")
            )
        if vals.get("route", "role") != "role":
            vals = {**vals, "role_id": False}
        return super().write(vals)
