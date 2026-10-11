from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_EMPLOYEE,
    MODEL_PERMISSION,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_ROLE,
)
from odoo.addons.sol_laboratory.constants.xml_ids import ADMINISTRATOR_GROUP, ADMINISTRATOR_PERSON, ADMINISTRATOR_ROLE


# Nhân Sự
class Person(models.Model):
    _name = MODEL_PERSON
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN]
    _inherits = {MODEL_EMPLOYEE: "employee_id"}
    # The permissions on the person decide; the employee is read and written for them.
    _check_inherits_access = False
    _description = "Person"
    _rec_names_search = ("name", "work_email")

    # The Odoo employee the person delegates to, holding their name, user, work contact and department.
    employee_id = fields.Many2one(MODEL_EMPLOYEE, required=True, ondelete="cascade", copy=False)
    # The Odoo user the person logs in as; empty for people who never sign in.
    user_id = fields.Many2one(related="employee_id.user_id", inherited=True, readonly=False, groups=ADMINISTRATOR_GROUP)
    # The contact holding the person's details: name, email, phone, address.
    work_contact_id = fields.Many2one(
        related="employee_id.work_contact_id", inherited=True, readonly=False, groups=ADMINISTRATOR_GROUP
    )
    # Department of the person. Odoo keeps it, like every field of the employee's version, where only employee
    # officers read; re-declared, it is read with full rights.
    department_id = fields.Many2one(related="employee_id.department_id", inherited=True, readonly=False)
    # False when the person is archived.
    active = fields.Boolean(default=True)
    # Roles the person holds.
    role_ids = fields.Many2many(
        MODEL_ROLE,
        "medilab_person_role_rel",
        "person_id",
        "role_id",
        ondelete="restrict",
        string="Roles",
        groups=ADMINISTRATOR_GROUP,
    )
    # Permissions given to the person directly, on top of their roles.
    permission_ids = fields.Many2many(
        MODEL_PERMISSION,
        "medilab_person_permission_rel",
        "person_id",
        "permission_id",
        string="Direct Permissions",
        groups=ADMINISTRATOR_GROUP,
    )
    # The login of the person's Odoo user; filling it on a person without a user creates the user.
    login = fields.Char(related="user_id.login", readonly=False, groups=ADMINISTRATOR_GROUP)

    _employee_unique = models.Constraint("UNIQUE(employee_id)", "This employee is already a person.")

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access("create")
        logins = []
        for vals in vals_list:
            employee_vals = self._pop_employee_vals(vals)
            for name in vals:
                if name in self._fields:
                    self.check_field_access(self._fields[name], "write")
            logins.append(vals.pop("login", False))
            vals["employee_id"] = self._employee_for(vals.get("employee_id"), employee_vals).id
        # Odoo would also require reading the employee, which only its own groups give; the person's access decides.
        people = super(Person, self.sudo()).create(vals_list).with_env(self.env)
        people.check_access("create")
        for person, login in zip(people, logins, strict=True):
            if login:
                person._set_login(login)
        people._sync_user_groups()
        return people

    def write(self, vals):
        vals = dict(vals)
        employee_vals = self._pop_employee_vals(vals)
        login = vals.pop("login", None)
        self._check_write(vals, employee_vals, login)
        previous_users = self.sudo().user_id if "employee_id" in vals else None
        result = super().write(vals) if vals else True
        if employee_vals:
            self.sudo().employee_id.write(employee_vals)
        if login is not None:
            for person in self:
                person._set_login(login)
        if "role_ids" in vals:
            self._check_administrator_role()
        if "active" in vals:
            employees = self.sudo().employee_id
            if vals["active"]:
                employees.action_unarchive()
            else:
                employees.action_archive()
            self.sudo().user_id.write({"active": vals["active"]})
        if "employee_id" in vals:
            self._strip_user_groups(previous_users - self.sudo().user_id)
        if {"role_ids", "permission_ids", "employee_id"} & set(vals):
            self._sync_user_groups()
        return result

    def action_open_user(self):
        # The user form is where Odoo administrators set the password.
        self.ensure_one()
        return self.user_id._get_records_action()

    @api.ondelete(at_uninstall=False)
    def _unlink_except_administrator(self):
        if self._administrator():
            raise UserError(self.env._("The person of Odoo's default administrator cannot be deleted."))

    def unlink(self):
        users = self.sudo().user_id
        result = super().unlink()
        self._strip_user_groups(users)
        return result

    def _pop_employee_vals(self, vals):
        # The employee's fields are written with full rights, once the person's own checks have passed.
        employee_vals = {}
        for name in [name for name in vals if name in self._fields and self._fields[name].inherited]:
            self.check_field_access(self._fields[name], "write")
            employee_vals[name] = vals.pop(name)
        return employee_vals

    def _employee_for(self, employee_id, employee_vals):
        employees = self.env[MODEL_EMPLOYEE].sudo()
        if employee_id:
            # Delegating to an existing employee changes their details, so it needs the right to edit them.
            self.env[MODEL_EMPLOYEE].browse(employee_id).check_access("write")
            employee = employees.browse(employee_id)
        else:
            # A user may already have an employee, such as the one Odoo's demo data gives the default administrator.
            employee = employees.env["res.users"].browse(employee_vals.get("user_id")).employee_id
        if not employee:
            return employees.create(employee_vals)
        if employee_vals:
            employee.write(employee_vals)
        return employee

    def _check_write(self, vals, employee_vals, login):
        if login is not None:
            self.check_field_access(self._fields["login"], "write")
            if login and len(self) > 1:
                raise UserError(self.env._("A login belongs to one person only."))
        if "employee_id" in vals and any(person.employee_id.id != vals["employee_id"] for person in self):
            self.env[MODEL_EMPLOYEE].browse(vals["employee_id"]).check_access("write")
        self._check_administrator_change(vals)
        if employee_vals or login is not None:
            self._check_permission("edit")

    def _check_administrator_change(self, vals):
        administrator = self._administrator()
        if not administrator:
            return
        if vals.get("active") is False:
            raise UserError(self.env._("The person of Odoo's default administrator cannot be archived."))
        administrator = administrator.sudo()
        if ("user_id" in vals and vals["user_id"] != administrator.user_id.id) or (
            "employee_id" in vals and vals["employee_id"] != administrator.employee_id.id
        ):
            raise UserError(self.env._("The person of Odoo's default administrator keeps their user."))

    def _check_administrator_role(self):
        administrator = self._administrator()
        if administrator and self.env.ref(ADMINISTRATOR_ROLE) not in administrator.sudo().role_ids:
            raise UserError(self.env._("The person of Odoo's default administrator keeps the administrator role."))

    def _administrator(self):
        return self & (self.env.ref(ADMINISTRATOR_PERSON, raise_if_not_found=False) or self.browse())

    def _set_login(self, login):
        self.ensure_one()
        person = self.sudo()
        if not login:
            if person.user_id:
                raise UserError(
                    self.env._(
                        "%s signs in, so their login cannot be emptied; archive the person instead.", person.name
                    )
                )
            return
        if person.user_id:
            person.user_id.login = login
            return
        person.user_id = (
            self.env["res.users"]
            .sudo()
            .create(
                {
                    "login": login,
                    "partner_id": person.work_contact_id.id,
                    "group_ids": [Command.set(self.env.ref("base.group_user").ids)],
                }
            )
        )

    def _sync_user_groups(self):
        internal = self.env.ref("base.group_user")
        for person in self.sudo().filtered("user_id"):
            user = person.user_id
            wanted = internal | person.role_ids.group_id | person.permission_ids.group_id
            commands = self.env[MODEL_PERMISSION]._group_commands(user.group_ids, wanted)
            if commands:
                user.group_ids = commands

    def _strip_user_groups(self, users):
        for user in users.sudo():
            commands = self.env[MODEL_PERMISSION]._group_commands(user.group_ids, user.browse().group_ids)
            if commands:
                user.group_ids = commands
