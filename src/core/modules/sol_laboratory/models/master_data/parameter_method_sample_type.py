from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.catalog import DEFAULTS_CHECKED_BY_PARAMETER
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_MEASUREMENT_UNIT,
    MODEL_PARAMETER_METHOD,
    MODEL_PARAMETER_METHOD_SAMPLE_TYPE,
    MODEL_PERMISSION_MIXIN,
    MODEL_SAMPLE_TYPE,
    MODEL_TEST_PARAMETER,
)
from odoo.addons.sol_laboratory.fields.nullable_float import NullableFloat


# Cấu Hình Áp Dụng Theo Loại Mẫu
class ParameterMethodSampleType(models.Model):
    _name = MODEL_PARAMETER_METHOD_SAMPLE_TYPE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Sample Type of a Way of Testing"
    _order = "parameter_id, sample_type_id, is_default desc, id"
    _permission_actions = ("create", "edit", "delete")

    # The parameter the way of testing tests, so each parameter and sample type keeps one default.
    parameter_id = fields.Many2one(MODEL_TEST_PARAMETER, required=True, ondelete="cascade", index=True)
    # The way of testing that applies to the sample type.
    parameter_method_id = fields.Many2one(
        MODEL_PARAMETER_METHOD,
        required=True,
        ondelete="cascade",
        index=True,
        string="Way of Testing",
        domain="[('parameter_id', '=', parameter_id)]",
    )
    # The sample type the way applies to; its narrower and broader types do not share it.
    sample_type_id = fields.Many2one(MODEL_SAMPLE_TYPE, required=True, ondelete="restrict", index=True)
    # The unit results of the way are expressed in on this sample type.
    unit_id = fields.Many2one(MODEL_MEASUREMENT_UNIT, required=True, ondelete="restrict", index=True)
    # Limit of detection, the lowest value the way detects, in the unit; empty when the way states none.
    lod = NullableFloat(string="LOD", min_display_digits=1)
    # Limit of quantification, the lowest value the way measures reliably, in the unit; empty when the way states none.
    loq = NullableFloat(string="LOQ", min_display_digits=1)
    # Decimals a result shows, such as 2 for 0.50; results copy it.
    result_decimals = fields.Integer()
    # True for the way the parameter is normally tested on this sample type.
    is_default = fields.Boolean(string="Default")
    # False when the way of testing is archived, so the row is not offered.
    way_active = fields.Boolean(related="parameter_method_id.active")

    _way_sample_type_unique = models.Constraint(
        "UNIQUE(parameter_method_id, sample_type_id)", "The way of testing already applies to this sample type."
    )
    _one_default = models.UniqueIndex(
        "(parameter_id, sample_type_id) WHERE is_default",
        "A parameter has only one default way of testing for each sample type.",
    )

    @api.depends("parameter_method_id", "sample_type_id")
    def _compute_display_name(self):
        for applicability in self:
            applicability.display_name = (
                f"{applicability.parameter_method_id.display_name} – {applicability.sample_type_id.name}"
            )

    @api.constrains("parameter_id", "parameter_method_id")
    def _check_parameter(self):
        for applicability in self:
            if applicability.parameter_method_id.parameter_id != applicability.parameter_id:
                raise ValidationError(
                    self.env._(
                        "%(way)s tests another parameter than %(parameter)s.",
                        way=applicability.parameter_method_id.display_name,
                        parameter=applicability.parameter_id.display_name,
                    )
                )

    @api.constrains("lod", "loq")
    def _check_detection_limits(self):
        for applicability in self:
            lod, loq = applicability.lod, applicability.loq
            if (lod is not False and lod < 0) or (loq is not False and loq < 0):
                raise ValidationError(self.env._("%s: LOD and LOQ cannot be negative.", applicability.display_name))
            if lod is not False and loq is not False and lod > loq:
                raise ValidationError(self.env._("%s: LOD cannot be greater than LOQ.", applicability.display_name))

    @api.constrains("is_default", "parameter_method_id")
    def _check_default_active(self):
        for applicability in self.filtered("is_default"):
            if not applicability.parameter_method_id.active:
                raise ValidationError(
                    self.env._(
                        "%s is archived and cannot be the default way of testing.",
                        applicability.parameter_method_id.display_name,
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("parameter_id") and vals.get("parameter_method_id"):
                vals["parameter_id"] = (
                    self.env[MODEL_PARAMETER_METHOD].browse(vals["parameter_method_id"]).parameter_id.id
                )
        self._unset_defaults(
            {(vals["parameter_id"], vals["sample_type_id"]) for vals in vals_list if vals.get("is_default")}
        )
        applicabilities = super().create(vals_list)
        applicabilities._offering_changed()
        return applicabilities

    def write(self, vals):
        before = self._pairs()
        if vals.get("is_default"):
            self._unset_defaults(
                {(applicability.parameter_id.id, applicability.sample_type_id.id) for applicability in self}, self.ids
            )
        result = super().write(vals)
        self._offering_changed(before)
        return result

    def unlink(self):
        pairs = self._pairs()
        result = super().unlink()
        self._offering_changed(pairs)
        return result

    def _in_use_domain(self):
        # A unit or sample type stays in use while the way of testing that applies it is active.
        return Domain("parameter_method_id.active", "=", True)

    def _pairs(self):
        return {(applicability.parameter_id, applicability.sample_type_id) for applicability in self}

    @api.model
    def _unset_defaults(self, pairs, keep=None):
        # Making a way the default replaces the previous default of the same parameter and sample type. The change is
        # flushed before the new default is saved, so the unique index never sees two defaults.
        if not pairs:
            return
        same_pair = Domain.OR(
            Domain("parameter_id", "=", parameter_id) & Domain("sample_type_id", "=", sample_type_id)
            for parameter_id, sample_type_id in pairs
        )
        previous = self.search(same_pair & Domain("is_default", "=", True)) - self.browse(keep)
        # The caller checks the defaults once the new one is saved.
        previous.with_context(**{DEFAULTS_CHECKED_BY_PARAMETER: True}).is_default = False
        previous.flush_recordset(["is_default"])

    def _offering_changed(self, extra_pairs=()):
        """Save the sample types the touched parameters are offered on, then check that each parameter and sample type
        an active way of testing applies to has exactly one default."""
        pairs = self.exists()._pairs() | set(extra_pairs)
        parameters = self.env[MODEL_TEST_PARAMETER].browse({parameter.id for parameter, _type in pairs})
        # A search through them, such as the portal catalog's, does not recompute them first.
        parameters.flush_recordset(["sample_type_ids"])
        if not self.env.context.get(DEFAULTS_CHECKED_BY_PARAMETER):
            parameters._check_defaults({sample_type for _parameter, sample_type in pairs})
