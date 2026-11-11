from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_ACCREDITATION_SCOPE_LINE,
    MODEL_AUDIT_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_SAMPLE_TYPE,
    MODEL_TEST_PARAMETER,
    MODEL_TESTING_METHOD,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_accreditation_scope_line as AccreditationScopeLineBase
else:
    AccreditationScopeLineBase = object


# Dòng Phạm Vi Công Nhận
class AccreditationScopeLine(models.Model, AccreditationScopeLineBase):
    _name = MODEL_ACCREDITATION_SCOPE_LINE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Accreditation Scope Line"
    _order = "certificate_id, id"
    _permission_actions = ("create", "edit", "delete")

    if not TYPE_CHECKING:
        # The certificate whose scope the line belongs to.
        certificate_id = fields.Many2one(
            MODEL_ACCREDITATION_CERTIFICATE,
            required=True,
            ondelete="cascade",
            index=True,
            string="Accreditation Certificate",
        )
        # The testing method the line accredits.
        method_id = fields.Many2one(
            MODEL_TESTING_METHOD, required=True, ondelete="restrict", index=True, string="Testing Method"
        )
        # Parameters the line accredits with its method.
        parameter_ids = fields.Many2many(
            MODEL_TEST_PARAMETER,
            "medilab_accreditation_scope_line_parameter_rel",
            "line_id",
            "parameter_id",
            ondelete="restrict",
            string="Parameters",
        )
        # Sample types the line accredits with its method; their narrower types are accredited too.
        sample_type_ids = fields.Many2many(
            MODEL_SAMPLE_TYPE,
            "medilab_accreditation_scope_line_sample_type_rel",
            "line_id",
            "sample_type_id",
            ondelete="restrict",
            string="Sample Types",
        )
        # True while the line names no parameter or no sample type, so it accredits nothing until an administrator
        # completes it, as the method-only lines of earlier certificates do.
        to_confirm = fields.Boolean(string="To Confirm", compute="_compute_to_confirm", store=True, index=True)

    @api.depends("certificate_id.code", "method_id.code")
    def _compute_display_name(self):
        for line in self:
            line.display_name = f"{line.certificate_id.code or ''} – {line.method_id.code or ''}"

    @api.depends("parameter_ids", "sample_type_ids")
    def _compute_to_confirm(self):
        for line in self:
            line.to_confirm = not line.parameter_ids or not line.sample_type_ids

    @api.constrains("method_id", "parameter_ids", "sample_type_ids")
    def _check_scope(self):
        for line in self:
            if not line.parameter_ids or not line.sample_type_ids:
                raise ValidationError(
                    self.env._(
                        "The scope line of %(method)s on %(certificate)s needs at least one parameter and one sample "
                        "type.",
                        method=line.method_id.code,
                        certificate=line.certificate_id.code,
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        self.env[MODEL_ACCREDITATION_CERTIFICATE]._recompute_accreditation(lines.method_id)
        return lines

    def write(self, vals):
        methods = self.method_id
        result = super().write(vals)
        self.env[MODEL_ACCREDITATION_CERTIFICATE]._recompute_accreditation(methods | self.method_id)
        return result

    def unlink(self):
        methods = self.method_id
        result = super().unlink()
        self.env[MODEL_ACCREDITATION_CERTIFICATE]._recompute_accreditation(methods)
        return result

    @api.model
    def _covered(self, keys, today=None):
        """Return the (method id, parameter id, sample type id) keys that a line of an active certificate valid on
        today covers: its method, one of its parameters and the sample type or one of its ancestors."""
        keys = {key for key in keys if all(key)}
        if not keys:
            return set()
        today = today or self.env[MODEL_ACCREDITATION_CERTIFICATE]._laboratory_today()
        lines = self.sudo().search(
            [
                ("method_id", "in", list({method_id for method_id, _, _ in keys})),
                ("certificate_id.active", "=", True),
                "|",
                ("certificate_id.valid_from", "=", False),
                ("certificate_id.valid_from", "<=", today),
                "|",
                ("certificate_id.valid_until", "=", False),
                ("certificate_id.valid_until", ">=", today),
            ]
        )
        scope = {}
        for line in lines:
            scope.setdefault(line.method_id.id, []).append((set(line.parameter_ids.ids), set(line.sample_type_ids.ids)))
        sample_types = (
            self.env[MODEL_SAMPLE_TYPE]
            .sudo()
            .with_context(active_test=False)
            .browse({sample_type_id for _, _, sample_type_id in keys})
        )
        ancestors = {
            sample_type.id: {int(part) for part in (sample_type.parent_path or "").split("/") if part}
            | {sample_type.id}
            for sample_type in sample_types
        }
        return {
            key
            for key in keys
            if any(
                key[1] in parameter_ids and ancestors.get(key[2], set()) & sample_type_ids
                for parameter_ids, sample_type_ids in scope.get(key[0], ())
            )
        }
