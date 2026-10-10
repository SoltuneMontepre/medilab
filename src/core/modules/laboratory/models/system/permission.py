from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command

from odoo.addons.laboratory.constants.models import MODEL_PERMISSION

MODULE = "laboratory"
DOCUMENT_MODEL_PREFIX = "medilab."
DEPARTMENT_FIELD = "department_id"
ADMINISTRATOR_GROUP = "laboratory.group_role_administrator"
# The Odoo operation each action is enforced with; sign has none, its group alone marks who may sign.
OPERATIONS = {"read": "read", "create": "create", "edit": "write", "archive": "write", "delete": "unlink"}
SCOPE_DOMAINS = {
    "all": "[(1, '=', 1)]",
    "own_department": (
        f"[('{DEPARTMENT_FIELD}.person_ids', 'any', [('user_id', '=', user.id), ('active', '=', True)])]"
    ),
}
IDENTITY_FIELDS = ("document_model", "action", "scope", "group_id")


# Quyền
class Permission(models.Model):
    _name = MODEL_PERMISSION
    _description = "Permission"
    _order = "document_model, action, scope"

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

    _code_unique = models.Constraint("UNIQUE(code)", "A permission with this code already exists.")
    _group_unique = models.Constraint("UNIQUE(group_id)", "Each permission has its own group.")
    _identity_unique = models.Constraint(
        "UNIQUE(document_model, action, scope)",
        "A permission for this action on this document type and scope already exists.",
    )

    @api.model
    def _selection_document_model(self):
        return [
            (name, self.env["ir.model"]._get(name).name)
            for name in sorted(self.env.registry)
            if name.startswith(DOCUMENT_MODEL_PREFIX) and not self.env[name]._abstract and not self.env[name]._transient
        ]

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
            scope = vals.get("scope", "all")
            self._check_scope(vals["document_model"], scope)
            code = self._make_code(vals["document_model"], vals["action"], scope)
            vals["group_id"] = groups.create({"name": f"Permission: {code}"}).id
        permissions = super().create(vals_list)
        permissions._generate_access()
        self.env.ref(ADMINISTRATOR_GROUP).sudo().implied_ids = [
            Command.link(group.id) for group in permissions.group_id
        ]
        return permissions

    def write(self, vals):
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
                    ", ".join(shipped.mapped("display_name")),
                )
            )

    def unlink(self):
        groups = self.group_id.sudo()
        self.env["ir.rule"].sudo().search([("groups", "in", groups.ids)]).unlink()
        self.env["ir.model.access"].sudo().search([("group_id", "in", groups.ids)]).unlink()
        result = super().unlink()
        groups.unlink()
        return result

    def _check_scope(self, document_model, scope):
        if scope == "own_department" and DEPARTMENT_FIELD not in self.env[document_model]._fields:
            raise ValidationError(
                self.env._(
                    "%s has no department, so a permission on it cannot be limited to the person's department.",
                    self.env["ir.model"]._get(document_model).name,
                )
            )

    def _generate_access(self):
        # External ids are created in the order group, access rule, record rule: uninstalling deletes the newest
        # first, so the rules go before the group they refer to.
        xml_ids = []
        for permission in self.sudo():
            suffix = permission.code.replace(".", "_")
            name = f"Permission: {permission.code}"
            xml_ids.append({"xml_id": f"{MODULE}.group_permission_{suffix}", "record": permission.group_id})
            operation = OPERATIONS.get(permission.action)
            if not operation:
                continue
            model = self.env["ir.model"]._get(permission.document_model)
            access = self.env["ir.model.access"].create(
                {
                    "name": name,
                    "model_id": model.id,
                    "group_id": permission.group_id.id,
                    f"perm_{operation}": True,
                }
            )
            rule = self.env["ir.rule"].create(permission._rule_values())
            xml_ids.append({"xml_id": f"{MODULE}.access_permission_{suffix}", "record": access})
            xml_ids.append({"xml_id": f"{MODULE}.rule_permission_{suffix}", "record": rule})
        for xml_id in xml_ids:
            xml_id["noupdate"] = True
        self.env["ir.model.data"].sudo()._update_xmlids(xml_ids)

    def _rule_values(self):
        self.ensure_one()
        operation = OPERATIONS[self.action]
        return {
            "name": f"Permission: {self.code}",
            "model_id": self.env["ir.model"]._get(self.document_model).id,
            "groups": [Command.link(self.group_id.id)],
            "domain_force": SCOPE_DOMAINS[self.scope],
            **{f"perm_{mode}": mode == operation for mode in ("read", "write", "create", "unlink")},
        }
