from odoo import models

UNCHECKED_PARENTS = "medilab_unchecked_parent_models"


# Accesses: a document whose own permissions govern the contact it delegates to does not need the contact's readers.
class IrAccess(models.Model):
    _inherit = "ir.access"

    def _get_groups_with_access(self, model_name, operation):
        # Odoo keeps only the groups that can also read the parent of an _inherits model, so a view would hide every
        # node with groups from people who hold only the document's permissions.
        if model_name in self.env.context.get(UNCHECKED_PARENTS, ()):
            return self.env["res.groups"].sudo().search([])
        model = self.env[model_name]
        accesses = self
        if model._inherits and not model._check_inherits_access:
            accesses = self.with_context(**{UNCHECKED_PARENTS: tuple(model._inherits)})
        return super(IrAccess, accesses)._get_groups_with_access(model_name, operation)
