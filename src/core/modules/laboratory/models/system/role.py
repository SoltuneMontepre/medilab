import re

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command

from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG
from odoo.addons.laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_PERMISSION,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_ROLE,
)
from odoo.addons.laboratory.constants.xml_ids import ADMINISTRATOR_GROUP, ADMINISTRATOR_ROLE, MODULE

CODE_PATTERN = re.compile(r"[a-z][a-z0-9_]*")


# Vai Trò
class Role(models.Model):
    _name = MODEL_ROLE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN]
    _description = "Role"
    _order = "code"
    _rec_names_search = ["name", "code"]

    # Unique code of the role: lowercase letters, digits and underscores; cannot change once the role exists.
    code = fields.Char(required=True, copy=False)
    # Role name in each language.
    name = fields.Char(required=True, translate=True)
    # The Odoo group generated for the role, which implies the groups of its permissions.
    group_id = fields.Many2one("res.groups", required=True, readonly=True, ondelete="restrict", copy=False)
    # Permissions the role contains.
    permission_ids = fields.Many2many(
        MODEL_PERMISSION,
        "medilab_role_permission_rel",
        "role_id",
        "permission_id",
        string="Permissions",
        groups=ADMINISTRATOR_GROUP,
    )
    # People who hold the role.
    person_ids = fields.Many2many(
        MODEL_PERSON, "medilab_person_role_rel", "role_id", "person_id", string="People", groups=ADMINISTRATOR_GROUP
    )

    _code_unique = models.Constraint("UNIQUE(code)", "A role with this code already exists.")
    _group_unique = models.Constraint("UNIQUE(group_id)", "Each role has its own group.")

    @api.model_create_multi
    def create(self, vals_list):
        groups = self.env["res.groups"].sudo()
        xml_ids = []
        for vals in vals_list:
            self._check_code(vals["code"])
            if not vals.get("group_id"):
                group = groups.create({"name": f"Role: {vals['code']}"})
                vals["group_id"] = group.id
                xml_ids.append({"xml_id": f"{MODULE}.group_role_{vals['code']}", "record": group, "noupdate": True})
        self.env["ir.model.data"].sudo()._update_xmlids(xml_ids)
        roles = super().create(vals_list)
        roles._sync_groups()
        return roles

    def write(self, vals):
        if "code" in vals and any(role.code != vals["code"] for role in self):
            raise UserError(self.env._("The code of a role cannot change; create another role."))
        if "group_id" in vals and any(role.group_id.id != vals["group_id"] for role in self):
            raise UserError(self.env._("The group of a role cannot change."))
        administrator = self & self.env.ref(ADMINISTRATOR_ROLE)
        if administrator and "name" in vals and administrator.name != vals["name"]:
            raise UserError(self.env._("The administrator role cannot be renamed."))
        permissions_before = administrator.permission_ids
        result = super().write(vals)
        if "permission_ids" in vals:
            if permissions_before - administrator.permission_ids:
                raise UserError(self.env._("The administrator role holds every permission; none can be removed."))
            self._sync_groups()
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_except_administrator(self):
        if self.env.ref(ADMINISTRATOR_ROLE) in self:
            raise UserError(self.env._("The administrator role cannot be deleted."))

    def unlink(self):
        groups = self.group_id.sudo()
        result = super().unlink()
        # When the module is uninstalled, the groups go through their own external ids, after the roles.
        if not self.env.context.get(MODULE_UNINSTALL_FLAG):
            groups.unlink()
        return result

    def _check_code(self, code):
        if not CODE_PATTERN.fullmatch(code or ""):
            raise ValidationError(
                self.env._(
                    "The role code %s may contain only lowercase letters, digits and underscores, "
                    "and starts with a letter.",
                    code,
                )
            )

    def _sync_groups(self):
        # A role group implies exactly the groups of its permissions; other implied groups, such as Odoo's settings
        # group implied by the administrator, are left as they are.
        for role in self.sudo():
            wanted = role.permission_ids.group_id
            implied = role.group_id.implied_ids
            permission_groups = self.env[MODEL_PERMISSION].sudo().search([("group_id", "in", implied.ids)]).group_id
            stale = permission_groups - wanted
            commands = [Command.unlink(group.id) for group in stale]
            commands += [Command.link(group.id) for group in wanted - implied]
            if commands:
                role.group_id.implied_ids = commands
