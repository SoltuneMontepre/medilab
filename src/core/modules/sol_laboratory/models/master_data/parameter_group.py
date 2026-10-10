from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import format_list

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_CODE_MIXIN,
    MODEL_PARAMETER_GROUP,
    MODEL_TEST_PARAMETER,
)


# Nhóm Chỉ Tiêu
class ParameterGroup(models.Model):
    _name = MODEL_PARAMETER_GROUP
    _inherit = [MODEL_ARCHIVE_MIXIN, MODEL_CODE_MIXIN]
    _description = "Parameter Group"
    _parent_store = True
    _order = "code"
    _rec_names_search = ("name", "code")

    # Unique code of the group, such as NCT.0001; filled from a sequence when left empty.
    code = fields.Char(required=True, copy=False)
    # Group name in each language.
    name = fields.Char(required=True, translate=True)
    # The group this one is a sub-group of; empty for a top-level group.
    parent_id = fields.Many2one(MODEL_PARAMETER_GROUP, ondelete="restrict", index=True)
    # Ids of the group and all its ancestors, such as 1/4/9/, so filtering by a group finds its sub-groups in one query.
    parent_path = fields.Char(index=True)
    # Sub-groups of this group.
    child_ids = fields.One2many(MODEL_PARAMETER_GROUP, "parent_id", string="Sub-groups")
    # Parameters in the group.
    parameter_ids = fields.Many2many(
        MODEL_TEST_PARAMETER, "medilab_test_parameter_group_rel", "group_id", "parameter_id", string="Parameters"
    )
    # False when the group is archived.
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a parameter group must be unique.")

    @api.constrains("parent_id")
    def _check_parent_id(self):
        parents_with_parameters = self.parent_id.with_context(active_test=False).filtered("parameter_ids")
        if parents_with_parameters:
            raise ValidationError(
                self.env._(
                    "A group that has parameters cannot have sub-groups: %s.",
                    format_list(self.env, parents_with_parameters.mapped("display_name")),
                )
            )

    @api.constrains("parameter_ids")
    def _check_parameter_ids(self):
        # Parameters added to or removed from a group follow the rules checked when the parameter is edited.
        self.env[MODEL_TEST_PARAMETER].with_context(active_test=False).search(
            ["|", ("group_ids", "in", self.ids), ("main_group_id", "in", self.ids)]
        )._check_groups()
