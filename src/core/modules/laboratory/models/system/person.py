from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from odoo.addons.laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_DEPARTMENT,
    MODEL_PERMISSION,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_ROLE,
)
from odoo.addons.laboratory.constants.xml_ids import ADMINISTRATOR_GROUP, ADMINISTRATOR_PERSON, ADMINISTRATOR_ROLE

CONTACT_FIELDS = ("name", "email", "phone")
RES_PARTNER = "res.partner"


# Nhân Sự
class Person(models.Model):
    _name = MODEL_PERSON
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN]
    _description = "Person"
    _rec_names_search = ["name", "email"]

    # The contact holding the person's details: name, email, phone, address.
    partner_id = fields.Many2one(RES_PARTNER, string="Contact", required=True, ondelete="restrict", copy=False)
    # The Odoo user the person logs in as; empty for people who never sign in.
    user_id = fields.Many2one("res.users", ondelete="restrict", copy=False, groups=ADMINISTRATOR_GROUP)
    # Department of the person.
    department_id = fields.Many2one(MODEL_DEPARTMENT, ondelete="restrict", index=True)
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
    # The person's name, held by their contact.
    name = fields.Char(related="partner_id.name", readonly=False, required=True)
    # The person's email address, held by their contact.
    email = fields.Char(related="partner_id.email", readonly=False)
    # The person's phone number, held by their contact.
    phone = fields.Char(related="partner_id.phone", readonly=False)
    # The login of the person's Odoo user; filling it on a person without a user creates the user.
    login = fields.Char(related="user_id.login", readonly=False, groups=ADMINISTRATOR_GROUP)

    _partner_unique = models.Constraint("UNIQUE(partner_id)", "This contact is already a person.")
    _user_unique = models.Constraint("UNIQUE(user_id)", "This user already belongs to another person.")

    @api.model_create_multi
    def create(self, vals_list):
        logins = []
        for vals in vals_list:
            contact = {field_name: vals.pop(field_name) for field_name in CONTACT_FIELDS if field_name in vals}
            if not vals.get("partner_id"):
                vals["partner_id"] = self.env[RES_PARTNER].sudo().create(contact).id
            elif contact:
                # An existing contact may belong to anyone, so only administrators change it with full rights.
                self.env[RES_PARTNER].browse(vals["partner_id"]).write(contact)
            if vals.get("login"):
                self._check_field_access(self._fields["login"], "write")
            logins.append(vals.pop("login", False))
        people = super().create(vals_list)
        for person, login in zip(people, logins, strict=True):
            if login:
                person._set_login(login)
        people._sync_user_groups()
        return people

    def write(self, vals):
        vals = dict(vals)
        contact = {field_name: vals.pop(field_name) for field_name in CONTACT_FIELDS if field_name in vals}
        login = vals.pop("login", None)
        self._check_write(vals, contact, login)
        previous_users = self.sudo().user_id
        result = super().write(vals) if vals else True
        if contact:
            self.sudo().partner_id.write(contact)
        if login is not None:
            for person in self:
                person._set_login(login)
        if "role_ids" in vals:
            self._check_administrator_role()
        if "active" in vals:
            self.sudo().user_id.write({"active": vals["active"]})
        if {"role_ids", "permission_ids", "user_id"} & set(vals):
            self._strip_user_groups(previous_users - self.sudo().user_id)
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

    def _check_write(self, vals, contact, login):
        # Contact details and the login are written outside Odoo's own field checks, so their access is checked here.
        if login is not None:
            self._check_field_access(self._fields["login"], "write")
            if login and len(self) > 1:
                raise UserError(self.env._("A login belongs to one person only."))
        if "partner_id" in vals and any(person.partner_id.id != vals["partner_id"] for person in self):
            self.env[RES_PARTNER].browse(vals["partner_id"]).check_access("write")
        self._check_administrator_change(vals)
        if contact or login is not None:
            self._check_permission("edit")

    def _check_administrator_change(self, vals):
        administrator = self._administrator()
        if not administrator:
            return
        if vals.get("active") is False:
            raise UserError(self.env._("The person of Odoo's default administrator cannot be archived."))
        if "user_id" in vals and vals["user_id"] != administrator.sudo().user_id.id:
            raise UserError(self.env._("The person of Odoo's default administrator keeps their user."))

    def _check_administrator_role(self):
        administrator = self._administrator()
        if administrator and self.env.ref(ADMINISTRATOR_ROLE) not in administrator.sudo().role_ids:
            raise UserError(self.env._("The person of Odoo's default administrator keeps the administrator role."))

    def _administrator(self):
        return self & self.env.ref(ADMINISTRATOR_PERSON, raise_if_not_found=False)

    def _set_login(self, login):
        # The Odoo user is created on the person's own contact, as an internal user.
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
                    "partner_id": person.partner_id.id,
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
