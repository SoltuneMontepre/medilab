from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import format_list

from odoo.addons.laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_CODE_MIXIN,
    MODEL_PARAMETER_GROUP,
    MODEL_PARAMETER_METHOD,
    MODEL_SAMPLE_TYPE,
    MODEL_TEST_PARAMETER,
)


# Chỉ Tiêu
class TestParameter(models.Model):
    _name = MODEL_TEST_PARAMETER
    _inherit = [MODEL_ARCHIVE_MIXIN, MODEL_CODE_MIXIN]
    _description = "Test Parameter"
    _order = "code"
    _rec_names_search = ["name", "code"]

    # Unique code staff and documents use for the parameter; filled from a sequence when left empty.
    code = fields.Char(required=True, copy=False, index="trigram")
    # Parameter name in each language.
    name = fields.Char(required=True, translate=True, index="trigram")
    # The group revenue reports count the parameter under; one of the parameter's groups.
    main_group_id = fields.Many2one(MODEL_PARAMETER_GROUP, required=True, ondelete="restrict", index=True)
    # Groups the parameter belongs to.
    group_ids = fields.Many2many(
        MODEL_PARAMETER_GROUP,
        "medilab_test_parameter_group_rel",
        "parameter_id",
        "group_id",
        ondelete="restrict",
        string="Groups",
    )
    # Sample types the parameter can be tested on.
    sample_type_ids = fields.Many2many(
        MODEL_SAMPLE_TYPE,
        "medilab_test_parameter_sample_type_rel",
        "parameter_id",
        "sample_type_id",
        ondelete="restrict",
        string="Sample Types",
    )
    # Ways the parameter can be tested.
    method_ids = fields.One2many(MODEL_PARAMETER_METHOD, "parameter_id", string="Ways of Testing")
    # False when the parameter is archived and no longer offered.
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a test parameter must be unique.")

    @api.constrains("group_ids", "main_group_id")
    def _check_groups(self):
        for parameter in self:
            if parameter.main_group_id not in parameter.group_ids:
                raise ValidationError(
                    self.env._("The main group of %s must be one of its groups.", parameter.display_name)
                )
            groups_with_sub_groups = parameter.group_ids.with_context(active_test=False).filtered("child_ids")
            if groups_with_sub_groups:
                raise ValidationError(
                    self.env._(
                        "Parameters belong only to groups without sub-groups: %s.",
                        format_list(self.env, groups_with_sub_groups.mapped("display_name")),
                    )
                )
