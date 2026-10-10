from lxml import etree

from odoo import api, models
from odoo.exceptions import AccessError
from odoo.fields import Domain
from odoo.tools.safe_eval import safe_eval

from odoo.addons.laboratory.constants.models import MODEL_PERMISSION, MODEL_PERMISSION_MIXIN
from odoo.addons.laboratory.constants.permissions import SCOPE_DOMAINS

EDITABLE_VIEW_TYPES = ("form", "list", "kanban")


# Splits Odoo's write right into the edit and archive permissions and checks each within its scope.
class PermissionMixin(models.AbstractModel):
    _name = MODEL_PERMISSION_MIXIN
    _description = "Permission Checks"
    # The actions a document type has permissions for; a signed document type adds sign.
    _permission_actions = ("read", "create", "edit", "archive", "delete")

    def _has_field_access(self, field, operation):
        # Without the archive permission, active is read-only, so the interface does not offer Archive. Other fields
        # stay open here because creating a record checks field write access too; write() checks the edit permission.
        if field.name == "active" and operation == "write" and not self._has_permission("archive"):
            return False
        return super()._has_field_access(field, operation)

    @api.model
    def get_view(self, view_id=None, view_type="form", **options):
        result = super().get_view(view_id, view_type, **options)
        # Archive also needs Odoo's write right, so the view is made read-only when only archiving is allowed.
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

    def _user_permissions(self, action):
        return (
            self.env[MODEL_PERMISSION]
            .sudo()
            .search(
                [
                    ("document_model", "=", self._name),
                    ("action", "=", action),
                    ("group_id", "in", self.env.user.all_group_ids.ids),
                ]
            )
        )

    def _has_permission(self, action):
        return self.env.su or bool(self._user_permissions(action))

    def _permission_domain(self, action):
        # The records the user may take the action on: the union of the scopes of their permissions for it.
        if self.env.su:
            return Domain.TRUE
        eval_context = {"user": self.env.user}
        return Domain.OR(
            Domain(safe_eval(SCOPE_DOMAINS[scope], eval_context))
            for scope in set(self._user_permissions(action).mapped("scope"))
        )

    def _check_permission(self, action):
        if self.env.su or not self:
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
                    action=dict(self.env[MODEL_PERMISSION]._fields["action"]._description_selection(self.env))[action],
                    records=", ".join(forbidden.sudo().mapped("display_name")),
                )
            )
