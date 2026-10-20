from lxml import etree

from odoo import api, models
from odoo.exceptions import AccessError
from odoo.fields import Domain
from odoo.tools import format_list
from odoo.tools.safe_eval import safe_eval

from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION, MODEL_PERMISSION_MIXIN
from odoo.addons.sol_laboratory.constants.permissions import SCOPE_DOMAINS

EDITABLE_VIEW_TYPES = ("form", "list", "kanban")


# Permission checks shared by document models.
class PermissionMixin(models.AbstractModel):
    _name = MODEL_PERMISSION_MIXIN
    _description = "Permission Checks"
    # The actions a document type has permissions for; a signed document type adds sign.
    _permission_actions = ("read", "create", "edit", "archive", "delete")

    def _has_field_access(self, field, operation):
        # Only active is gated here, because create() checks field access too; write() checks edit.
        if field.name == "active" and operation == "write" and not self._has_permission("archive"):
            return False
        return super()._has_field_access(field, operation)

    @api.model
    def get_view(self, view_id=None, view_type="form", **options):
        result = super().get_view(view_id, view_type, **options)
        if view_type in EDITABLE_VIEW_TYPES and not self._has_permission("edit"):
            root = etree.fromstring(result["arch"])
            root.set("edit", "False")
            result["arch"] = etree.tostring(root, encoding="unicode")
        return result

    def write(self, vals):
        if "active" in vals:
            self._check_permission("archive")
        if set(vals) - {"active"}:
            self._check_permission("edit")
        return super().write(vals)

    @api.model
    def _supported_permission_actions(self):
        return tuple(action for action in self._permission_actions if action != "archive" or self._active_name)

    def _user_scopes(self, action):
        group_ids = set(self.env.user._get_group_ids())
        return {
            scope
            for group_id, scope in self.env[MODEL_PERMISSION]._permission_scopes(self._name, action)
            if group_id in group_ids
        }

    def _has_permission(self, action):
        return self.env.su or bool(self._user_scopes(action))

    def _permission_domain(self, action):
        # The records the user may take the action on: the union of the scopes of their permissions for it.
        if self.env.su:
            return Domain.TRUE
        eval_context = self.env["ir.access"]._eval_context()
        return Domain.OR(Domain(safe_eval(SCOPE_DOMAINS[scope], eval_context)) for scope in self._user_scopes(action))

    def _check_permission(self, action):
        if self.env.su or not self or "all" in self._user_scopes(action):
            return
        allowed = (
            self.sudo()
            .with_context(active_test=False)
            .search(Domain("id", "in", self.ids) & self._permission_domain(action))
        )
        forbidden = self - allowed.with_env(self.env)
        if forbidden:
            raise AccessError(
                self.env._(
                    "You are not allowed to %(action)s these records: %(records)s",
                    action=self.env[MODEL_PERMISSION]._action_label(action),
                    records=format_list(self.env, forbidden.sudo().mapped("display_name")),
                )
            )
