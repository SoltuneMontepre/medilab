from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ACCESS

if TYPE_CHECKING:
    from medilab_model_types import Model_ir_access as IrAccessBase
else:
    IrAccessBase = object

UNCHECKED_PARENTS = "medilab_unchecked_parent_models"


# Accesses: a document whose own permissions govern the contact it delegates to does not need the contact's readers.
class IrAccess(models.Model, IrAccessBase):
    _inherit = MODEL_IR_ACCESS

    def _get_groups_with_access(self, model_name, operation):
        # Odoo keeps only the groups that can also read the parent of an _inherits model, so a view would hide every
        # node with groups from people who hold only the document's permissions.
        if model_name in self.env.context.get(UNCHECKED_PARENTS, ()):
            groups = self.env["res.groups"].sudo()
            return groups.browse(groups._get_group_definitions().get_all_ids())
        model = self.env[model_name]
        accesses = self
        if model._inherits and not model._check_inherits_access:
            accesses = self.with_context(**{UNCHECKED_PARENTS: tuple(model._inherits)})
        return super(IrAccess, accesses)._get_groups_with_access(model_name, operation)
