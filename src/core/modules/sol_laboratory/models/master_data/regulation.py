from datetime import date
from typing import TYPE_CHECKING, Literal

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import format_date, format_list

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_PARAMETER_METHOD_SAMPLE_TYPE,
    MODEL_PERMISSION_MIXIN,
    MODEL_REGULATION,
    MODEL_REGULATION_LIMIT,
    MODEL_SAMPLE,
    MODEL_SAMPLE_TYPE,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_regulation as RegulationBase
else:
    RegulationBase = object


# Quy Chuẩn
class Regulation(models.Model, RegulationBase):
    _name = MODEL_REGULATION
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Regulation"
    _rec_name = "code"
    _order = "code"
    _rec_names_search = ("code", "name")
    _permission_actions = ("create", "edit", "archive", "delete")
    _audit_children = ("limit_ids",)

    if not TYPE_CHECKING:
        # Unique reference of the regulation, such as QCVN 6-1:2010/BYT.
        code = fields.Char(required=True, copy=False, index="trigram")
        # Title of the regulation in each language.
        name = fields.Char(required=True, translate=True, index="trigram")
        # The ministry or body that issued the regulation.
        issuing_authority = fields.Char()
        # First day the regulation is in force; empty means in force from any date.
        valid_from = fields.Date()
        # Last day the regulation is in force; empty means in force until any date.
        valid_until = fields.Date()
        # Sample types the regulation applies to, with their narrower types.
        sample_type_ids = fields.Many2many(
            MODEL_SAMPLE_TYPE,
            "medilab_regulation_sample_type_rel",
            "regulation_id",
            "sample_type_id",
            ondelete="restrict",
            string="Sample Types",
        )
        # Limits the regulation sets, one per parameter and sample type.
        limit_ids = fields.One2many(MODEL_REGULATION_LIMIT, "regulation_id", string="Limits")
        # Sample types picked on the form to add a limit row for each parameter offered on them; never saved.
        add_sample_type_ids = fields.Many2many(
            MODEL_SAMPLE_TYPE,
            string="Add Parameters For",
            compute="_compute_add_sample_type_ids",
            readonly=False,
        )
        # Parameters the regulation limits on some sample type but not on another covered type they are offered on.
        missing_limits = fields.Char(compute="_compute_missing_limits")
        # False when the regulation is archived.
        active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The reference of a regulation must be unique.")

    def _compute_add_sample_type_ids(self):
        self.add_sample_type_ids = False

    @api.depends("sample_type_ids", "limit_ids.parameter_id", "limit_ids.sample_type_id")
    def _compute_missing_limits(self):
        for regulation in self:
            limited = {(limit.parameter_id, limit.sample_type_id) for limit in regulation.limit_ids}
            covered = regulation._covered_types()
            missing = [
                f"{parameter.display_name} – {sample_type.display_name}"
                for parameter in regulation.limit_ids.parameter_id
                for sample_type in parameter.sample_type_ids & covered
                if (parameter, sample_type) not in limited
            ]
            regulation.missing_limits = format_list(self.env, missing) if missing else False

    @api.onchange("add_sample_type_ids")
    def _onchange_add_sample_type_ids(self):
        """Prepare a limit row for each parameter offered on the picked sample types that has none, with the unit of its
        default way of testing; the bounds are left for the administrator to enter."""
        if not self.add_sample_type_ids:
            return
        taken = {(limit.parameter_id.id, limit.sample_type_id.id) for limit in self.limit_ids}
        defaults = self.env[MODEL_PARAMETER_METHOD_SAMPLE_TYPE].search(
            [
                ("sample_type_id", "in", self.add_sample_type_ids._origin.ids),
                ("is_default", "=", True),
                ("parameter_method_id.active", "=", True),
            ],
            order="parameter_id, sample_type_id",
        )
        limits = self.env[MODEL_REGULATION_LIMIT]
        for default in defaults:
            if (default.parameter_id.id, default.sample_type_id.id) not in taken:
                limits |= limits.new(
                    {
                        "parameter_id": default.parameter_id.id,
                        "sample_type_id": default.sample_type_id.id,
                        "unit_id": default.unit_id.id,
                    }
                )
        self.limit_ids |= limits
        self.add_sample_type_ids = False

    @api.constrains("valid_from", "valid_until")
    def _check_validity_dates(self):
        for regulation in self:
            if regulation.valid_from and regulation.valid_until and regulation.valid_from > regulation.valid_until:
                raise ValidationError(
                    self.env._(
                        "The first valid day of regulation %s cannot be after its last valid day.", regulation.code
                    )
                )

    @api.constrains("sample_type_ids")
    def _check_limit_scope(self):
        for regulation in self:
            outside = [limit for limit in regulation.limit_ids if not regulation._covers(limit.sample_type_id)]
            if outside:
                raise ValidationError(
                    self.env._(
                        "%(regulation)s does not apply to the sample type of these limits: %(limits)s. Keep their "
                        "sample types in its scope or remove the limits first.",
                        regulation=regulation.code,
                        limits=format_list(self.env, [limit._label() for limit in outside]),
                    )
                )

    def _covered_types(self):
        """The sample types the regulation names and their narrower types."""
        self.ensure_one()
        if not self.sample_type_ids:
            return self.env[MODEL_SAMPLE_TYPE]
        return self.env[MODEL_SAMPLE_TYPE].search([("id", "child_of", self.sample_type_ids._origin.ids)])

    def _covers(self, sample_type):
        self.ensure_one()
        ancestors = {int(part) for part in (sample_type.parent_path or "").split("/") if part}
        return bool(ancestors & set(self.sample_type_ids._origin.ids))

    def _expired(self, day: date):
        self.ensure_one()
        return bool(self.valid_until) and self.valid_until < day

    def _expiry_notice(self) -> str | Literal[False]:
        """Why a sample keeps a regulation that is no longer in force, or False while it is."""
        self.ensure_one()
        if not self._expired(self.env[MODEL_SAMPLE]._company_today()):
            return False
        return self.env._(
            "%(regulation)s is no longer in force: its last valid day was %(day)s. The sample keeps it.",
            regulation=self.code,
            day=format_date(self.env, self.valid_until),
        )

    def _check_selectable(self, sample_type):
        """Refuse choosing the regulation today for a sample of the sample type: it is archived, not yet or no longer in
        force, or it does not apply to the type."""
        today = self.env[MODEL_SAMPLE]._company_today()
        for regulation in self:
            if not regulation.active:
                raise ValidationError(self.env._("%s is archived and cannot be chosen.", regulation.code))
            if regulation.valid_from and regulation.valid_from > today:
                raise ValidationError(
                    self.env._(
                        "%(regulation)s is not in force yet: it applies from %(day)s.",
                        regulation=regulation.code,
                        day=format_date(self.env, regulation.valid_from),
                    )
                )
            if regulation._expired(today):
                raise ValidationError(
                    self.env._(
                        "%(regulation)s is no longer in force: its last valid day was %(day)s.",
                        regulation=regulation.code,
                        day=format_date(self.env, regulation.valid_until),
                    )
                )
            if not regulation._covers(sample_type):
                raise ValidationError(
                    self.env._(
                        "%(regulation)s does not apply to %(sample_type)s.",
                        regulation=regulation.code,
                        sample_type=sample_type.display_name,
                    )
                )
