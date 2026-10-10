from odoo import api, fields, models, tools
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools import format_list

from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG
from odoo.addons.laboratory.constants.models import MODEL_PERMISSION, MODEL_PERMISSION_MIXIN, MODEL_PERSON, MODEL_ROLE
from odoo.addons.laboratory.constants.permissions import DEPARTMENT_FIELD, OPERATIONS, SCOPE_DOMAINS
from odoo.addons.laboratory.constants.xml_ids import ADMINISTRATOR_GROUP, ADMINISTRATOR_ROLE, MODULE

DOCUMENT_MODEL_PREFIX = "medilab."
IR_MODEL = "ir.model"
IDENTITY_FIELDS = ("document_model", "action", "scope", "group_id")
# Who holds a permission is set from the role or the person, where the groups are kept in sync.
HOLDER_FIELDS = ("role_ids", "person_ids")
# Actions enforced through Odoo's write operation, which only the permission mixin splits into edit and archive.
WRITE_ACTIONS = ("edit", "archive")


# Quyền
class Permission(models.Model):
    _name = MODEL_PERMISSION
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Permission"
    _order = "document_model, action, scope"
    # Permissions come with modules: they are read and renamed on the screen, never created or deleted there.
    _permission_actions = ("read", "edit")

    # Unique code derived from the document type, action and scope, such as sample.edit.own_department.
    code = fields.Char(compute="_compute_code", store=True, required=True, precompute=True)
    # Permission name in each language.
    name = fields.Char(required=True, translate=True)
    # Technical name of the document type, such as medilab.sample; cannot change once the permission exists.
    document_model = fields.Selection(selection="_selection_document_model", string="Document Type", required=True)
    # read, create, edit, archive, delete or sign; cannot change once the permission exists.
    action = fields.Selection(
        [
            ("read", "Read"),
            ("create", "Create"),
            ("edit", "Edit"),
            ("archive", "Archive"),
            ("delete", "Delete"),
            ("sign", "Sign"),
        ],
        required=True,
    )
    # all for every record, or own_department for records of the person's department only; cannot change once
    # the permission exists.
    scope = fields.Selection(
        [("all", "All records"), ("own_department", "Own department")], required=True, default="all"
    )
    # The Odoo group generated for the permission, which carries its access rule and record rule.
    group_id = fields.Many2one("res.groups", required=True, readonly=True, ondelete="restrict", copy=False)
    # Roles that contain the permission.
    role_ids = fields.Many2many(
        MODEL_ROLE,
        "medilab_role_permission_rel",
        "permission_id",
        "role_id",
        string="Roles",
        groups=ADMINISTRATOR_GROUP,
    )
    # People given the permission directly.
    person_ids = fields.Many2many(
        MODEL_PERSON,
        "medilab_person_permission_rel",
        "permission_id",
        "person_id",
        string="People",
        groups=ADMINISTRATOR_GROUP,
    )

    _code_unique = models.Constraint("UNIQUE(code)", "A permission with this code already exists.")
    _group_unique = models.Constraint("UNIQUE(group_id)", "Each permission has its own group.")
    _identity_unique = models.Constraint(
        "UNIQUE(document_model, action, scope)",
        "A permission for this action on this document type and scope already exists.",
    )

    @api.model
    def _selection_document_model(self):
        names = [
            name
            for name, model in self.env.registry.items()
            if name.startswith(DOCUMENT_MODEL_PREFIX) and not model._abstract and not model._transient
        ]
        labels = {model.model: model.name for model in self.env[IR_MODEL].sudo().search([("model", "in", names)])}
        return sorted((name, labels.get(name, name)) for name in names)

    @api.model
    @tools.ormcache("document_model", "action")
    def _permission_scopes(self, document_model, action):
        # (group id, scope) of every permission for the action on the document type. A permission keeps its document
        # type, action and scope, so the cache is cleared only when permissions are created or deleted.
        permissions = self.sudo().search([("document_model", "=", document_model), ("action", "=", action)])
        return tuple((permission.group_id.id, permission.scope) for permission in permissions)

    @api.model
    def _make_code(self, document_model, action, scope):
        return f"{document_model.removeprefix(DOCUMENT_MODEL_PREFIX)}.{action}.{scope}"

    @api.depends("document_model", "action", "scope")
    def _compute_code(self):
        for permission in self:
            permission.code = self._make_code(permission.document_model, permission.action, permission.scope)

    @api.model_create_multi
    def create(self, vals_list):
        groups = self.env["res.groups"].sudo()
        for vals in vals_list:
            self._check_holders(vals)
            scope = vals.get("scope", "all")
            self._check_action(vals["document_model"], vals["action"], scope)
            code = self._make_code(vals["document_model"], vals["action"], scope)
            vals["group_id"] = groups.create({"name": f"Permission: {code}"}).id
        permissions = super().create(vals_list)
        permissions._generate_access()
        self.env.registry.clear_cache()
        self.env.ref(ADMINISTRATOR_ROLE).sudo().permission_ids = [Command.link(p.id) for p in permissions]
        return permissions

    def write(self, vals):
        self._check_holders(vals)
        for permission in self:
            for field_name in IDENTITY_FIELDS:
                if field_name not in vals:
                    continue
                current = permission[field_name]
                if permission._fields[field_name].type == "many2one":
                    current = current.id
                if current != vals[field_name]:
                    raise UserError(
                        self.env._(
                            "The document type, action and scope of %s cannot change; create another permission.",
                            permission.display_name,
                        )
                    )
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_shipped(self):
        external_ids = self._get_external_ids()
        shipped = self.filtered(lambda p: any(not xml_id.startswith("__") for xml_id in external_ids[p.id]))
        if shipped:
            raise UserError(
                self.env._(
                    "These permissions come with a module and cannot be deleted: %s",
                    format_list(self.env, shipped.mapped("display_name")),
                )
            )

    def unlink(self):
        # When the module is uninstalled, the generated records go through their own external ids, newest first.
        if self.env.context.get(MODULE_UNINSTALL_FLAG):
            return super().unlink()
        groups = self.group_id.sudo()
        for permission in self:
            for kind in ("rule", "access"):
                generated = self.env.ref(permission._generated_xml_id(kind), raise_if_not_found=False)
                if generated:
                    generated.sudo().unlink()
        shared = self.env["ir.rule"].sudo().search([("groups", "in", groups.ids)])
        if shared:
            raise UserError(
                self.env._(
                    "These record rules still use the permission's group: %s",
                    format_list(self.env, shared.mapped("name")),
                )
            )
        result = super().unlink()
        groups.unlink()
        self.env.registry.clear_cache()
        return result

    def _check_holders(self, vals):
        if set(HOLDER_FIELDS) & set(vals):
            raise UserError(self.env._("Give a permission to roles from the role, and to people from the person."))

    def _check_action(self, document_model, action, scope):
        model = self.env[document_model]
        label = self.env[IR_MODEL]._get(document_model).name
        if scope == "own_department" and DEPARTMENT_FIELD not in model._fields:
            raise ValidationError(
                self.env._(
                    "%s has no department, so a permission on it cannot be limited to the person's department.",
                    label,
                )
            )
        if document_model not in self.env.registry[MODEL_PERMISSION_MIXIN]._inherit_children:
            if action in WRITE_ACTIONS:
                raise ValidationError(
                    self.env._(
                        "%s does not tell editing from archiving yet, so it has no edit or archive permission.", label
                    )
                )
        elif action not in model._supported_permission_actions():
            raise ValidationError(
                self.env._(
                    "%(document_type)s has no %(action)s permission.",
                    document_type=label,
                    action=self._action_label(action),
                )
            )

    def _generate_access(self):
        # External ids are created in the order group, access rule, record rule: uninstalling deletes the newest
        # first, so the rules go before the group they refer to.
        xml_ids = []
        for permission in self.sudo():
            records = {"group": permission.group_id}
            if permission.action in OPERATIONS:
                records["access"] = self.env["ir.model.access"].sudo().create(permission._access_values())
                records["rule"] = self.env["ir.rule"].sudo().create(permission._rule_values())
            xml_ids += [
                {"xml_id": permission._generated_xml_id(kind), "record": record, "noupdate": True}
                for kind, record in records.items()
            ]
        self.env["ir.model.data"].sudo()._update_xmlids(xml_ids)

    def _generated_xml_id(self, kind):
        # The external id of the group, access rule or record rule generated for the permission.
        return f"{MODULE}.{kind}_permission_{self.code.replace('.', '_')}"

    @api.model
    def _action_label(self, action):
        return dict(self._fields["action"]._description_selection(self.env))[action]

    @api.model
    def _group_commands(self, current, wanted):
        # Commands that make the groups of roles and permissions among current exactly wanted; any other group is
        # left as it is.
        managed = (
            self.env[MODEL_ROLE].sudo().search([("group_id", "in", current.ids)]).group_id
            | self.sudo().search([("group_id", "in", current.ids)]).group_id
        )
        return [Command.unlink(group.id) for group in managed - wanted] + [
            Command.link(group.id) for group in wanted - current
        ]

    def _access_values(self):
        self.ensure_one()
        return {
            "name": f"Permission: {self.code}",
            "model_id": self.env[IR_MODEL]._get(self.document_model).id,
            "group_id": self.group_id.id,
            f"perm_{OPERATIONS[self.action]}": True,
        }

    def _rule_values(self):
        self.ensure_one()
        operation = OPERATIONS[self.action]
        return {
            "name": f"Permission: {self.code}",
            "model_id": self.env[IR_MODEL]._get(self.document_model).id,
            "groups": [Command.link(self.group_id.id)],
            "domain_force": SCOPE_DOMAINS[self.scope],
            **{f"perm_{mode}": mode == operation for mode in ("read", "write", "create", "unlink")},
        }
