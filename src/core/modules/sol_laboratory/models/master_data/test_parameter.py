from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import format_list

from odoo.addons.sol_laboratory.constants.catalog import DEFAULTS_CHECKED, DEFAULTS_CHECKED_BY_PARAMETER
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_CODE_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_PARAMETER_GROUP,
    MODEL_PARAMETER_METHOD,
    MODEL_PARAMETER_METHOD_SAMPLE_TYPE,
    MODEL_PERMISSION_MIXIN,
    MODEL_SAMPLE_TYPE,
    MODEL_TEST_PARAMETER,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_parameter as TestParameterBase
else:
    TestParameterBase = object


# Chỉ Tiêu
class TestParameter(models.Model, TestParameterBase):
    _name = MODEL_TEST_PARAMETER
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_CODE_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Test Parameter"
    _order = "code"
    _rec_names_search = ("name", "code")
    _permission_actions = ("create", "edit", "archive")
    _audit_children = ("method_ids", "applicability_ids")

    if not TYPE_CHECKING:
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
        # Sample types the parameter is offered on: those an active way of testing explicitly applies to.
        sample_type_ids = fields.Many2many(
            MODEL_SAMPLE_TYPE,
            "medilab_test_parameter_sample_type_rel",
            "parameter_id",
            "sample_type_id",
            ondelete="restrict",
            string="Sample Types",
            compute="_compute_sample_type_ids",
            store=True,
        )
        # Ways the parameter can be tested.
        method_ids = fields.One2many(MODEL_PARAMETER_METHOD, "parameter_id", string="Ways of Testing")
        # The sample types each way of testing applies to, with their unit, detection limits and default.
        applicability_ids = fields.One2many(
            MODEL_PARAMETER_METHOD_SAMPLE_TYPE, "parameter_id", string="Sample Types of the Ways of Testing"
        )
        # False when the parameter is archived and no longer offered.
        active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a test parameter must be unique.")

    @api.depends("applicability_ids.sample_type_id", "applicability_ids.parameter_method_id.active")
    def _compute_sample_type_ids(self):
        for parameter in self:
            parameter.sample_type_ids = parameter._offered_applicabilities().sample_type_id

    @api.model_create_multi
    def create(self, vals_list):
        checked = self.with_context(**{DEFAULTS_CHECKED_BY_PARAMETER: DEFAULTS_CHECKED})
        parameters = super(TestParameter, checked).create(vals_list)
        parameters = parameters.with_env(self.env)
        parameters._check_defaults()
        return parameters

    def write(self, vals):
        checked = self.with_context(**{DEFAULTS_CHECKED_BY_PARAMETER: DEFAULTS_CHECKED})
        result = super(TestParameter, checked).write(vals)
        if {"method_ids", "applicability_ids"} & set(vals):
            self.with_context(active_test=False).method_ids.filtered(
                lambda way: not way.active
            )._refuse_archiving_defaults()
            self._check_defaults()
        return result

    def _offered_applicabilities(self):
        return self.applicability_ids.filtered(lambda applicability: applicability.parameter_method_id.active)

    def _check_defaults(self, sample_types=None):
        """Refuse a parameter and sample type that an active way of testing applies to without exactly one default.

        Only the given sample types are checked, or all of the parameter's when none are given.
        """
        missing = []
        for parameter in self.exists():
            offered = parameter._offered_applicabilities()
            for sample_type in offered.sample_type_id:
                if sample_types is not None and sample_type not in sample_types:
                    continue
                on_type = offered.filtered(lambda a, sample_type=sample_type: a.sample_type_id == sample_type)
                if len(on_type.filtered("is_default")) != 1:
                    missing.append(f"{parameter.display_name} – {sample_type.name}")
        if missing:
            raise ValidationError(
                self.env._(
                    "Choose one default way of testing for each sample type: %s.", format_list(self.env, missing)
                )
            )

    def _order_refusal(self, sample_type):
        """Why the parameter cannot be ordered on the sample type, or False when it can.

        It cannot when no active way of testing applies to the sample type, or when its default way is unavailable and
        no other way is, since another way is never chosen silently.
        """
        self.ensure_one()
        default = self._default_way(sample_type)
        if not default:
            return self.env._(
                "%(parameter)s is not offered on %(sample_type)s.",
                parameter=self.display_name,
                sample_type=sample_type.display_name,
            )
        reason = default._unavailable_reason()
        if reason and not self._available_alternatives(sample_type):
            return self.env._(
                "%(parameter)s cannot be ordered on %(sample_type)s: its default way of testing is unavailable and no "
                "other way is. %(reason)s",
                parameter=self.display_name,
                sample_type=sample_type.display_name,
                reason=reason,
            )
        return False

    def _default_way_notice(self, sample_type):
        """Why the default way of testing on the sample type is unavailable and which ways can be chosen instead, or
        False when it is available."""
        self.ensure_one()
        default = self._default_way(sample_type)
        reason = default and default._unavailable_reason()
        if not reason:
            return False
        return self.env._(
            "The default way of testing %(parameter)s on %(sample_type)s is unavailable. %(reason)s Choose one of: "
            "%(ways)s.",
            parameter=self.display_name,
            sample_type=sample_type.display_name,
            reason=reason,
            ways=format_list(self.env, self._available_alternatives(sample_type).mapped("display_name")),
        )

    def _available_alternatives(self, sample_type):
        self.ensure_one()
        offered = self._offered_applicabilities().filtered(
            lambda applicability: applicability.sample_type_id == sample_type and not applicability.is_default
        )
        return offered.parameter_method_id.filtered(lambda way: not way._unavailable_reason())

    def _default_way(self, sample_type):
        """The way of testing the parameter is normally tested by on the sample type; empty when it has none."""
        self.ensure_one()
        applicability = self.applicability_ids.filtered(
            lambda a: a.sample_type_id == sample_type and a.is_default and a.parameter_method_id.active
        )
        return applicability.parameter_method_id

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
