from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_date, format_list

from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG
from odoo.addons.sol_laboratory.constants.catalog import DEFAULTS_CHECKED, DEFAULTS_CHECKED_BY_PARAMETER
from odoo.addons.sol_laboratory.constants.departments import DEPARTMENT_DOMAIN
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_DEPARTMENT,
    MODEL_LOCK_MIXIN,
    MODEL_PARAMETER_METHOD,
    MODEL_PARAMETER_METHOD_MACHINE,
    MODEL_PARAMETER_METHOD_SAMPLE_TYPE,
    MODEL_PERMISSION_MIXIN,
    MODEL_SUBCONTRACTOR,
    MODEL_TEST_PARAMETER,
    MODEL_TESTING_METHOD,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_parameter_method as ParameterMethodBase
else:
    ParameterMethodBase = object


# Cách Thử
class ParameterMethod(models.Model, ParameterMethodBase):
    _name = MODEL_PARAMETER_METHOD
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Way of Testing"
    _order = "parameter_id, id"
    _rec_names_search = ("parameter_id", "method_id")
    # Ways of testing are archived, never deleted, so they have no delete permission.
    _permission_actions = ("create", "edit", "archive")

    if not TYPE_CHECKING:
        # The parameter being tested.
        parameter_id = fields.Many2one(MODEL_TEST_PARAMETER, required=True, ondelete="restrict")
        # The method used to test it.
        method_id = fields.Many2one(
            MODEL_TESTING_METHOD, required=True, ondelete="restrict", index=True, string="Testing Method"
        )
        # The subcontractor that tests it; empty when the laboratory tests it in-house. Only an active subcontractor with a
        # valid accreditation is offered, also where the list disables the active test to show archived ways of testing.
        subcontractor_id = fields.Many2one(
            MODEL_SUBCONTRACTOR,
            ondelete="restrict",
            index=True,
            domain=[("active", "=", True), ("accreditation_expired", "=", False)],
        )
        # The department that tests it in-house; empty when a subcontractor tests it.
        department_id = fields.Many2one(MODEL_DEPARTMENT, ondelete="restrict", index=True, domain=DEPARTMENT_DOMAIN)
        # True while this in-house way of testing's method is on an accreditation certificate valid that day.
        is_accredited = fields.Boolean(
            string="Accredited",
            compute="_compute_is_accredited",
            store=True,
            readonly=True,
        )
        # True when its results may be negative, such as a redox potential or a temperature in °C.
        allows_negative = fields.Boolean(string="Negative Results")
        # The sample types the way applies to, with the unit, detection limits and default on each.
        applicability_ids = fields.One2many(
            MODEL_PARAMETER_METHOD_SAMPLE_TYPE, "parameter_method_id", string="Sample Types"
        )
        # False when this way of testing is archived.
        active = fields.Boolean(default=True)

    _parameter_method_unique = models.UniqueIndex(
        "(parameter_id, method_id, COALESCE(subcontractor_id, 0)) WHERE active",
        "The parameter is already tested with this method by the same laboratory.",
    )

    @api.depends("parameter_id", "method_id", "subcontractor_id")
    def _compute_display_name(self):
        for pair in self:
            name = f"{pair.parameter_id.name} – {pair.method_id.code}"
            pair.display_name = f"{name} ({pair.subcontractor_id.name})" if pair.subcontractor_id else name

    @api.depends("subcontractor_id", "method_id")
    def _compute_is_accredited(self):
        in_house = self.filtered(lambda pair: not pair.subcontractor_id)
        covered = self.env[MODEL_ACCREDITATION_CERTIFICATE]._accredited_methods(in_house.method_id)
        for pair in self:
            pair.is_accredited = not pair.subcontractor_id and pair.method_id in covered

    def _recompute_is_accredited(self):
        # Certificates and the day also change the mark, and the compute cannot depend on them.
        self.env.add_to_compute(self._fields["is_accredited"], self)
        self.flush_recordset(["is_accredited"])

    @api.model
    def _recompute_for_methods(self, methods):
        """Recompute pairs for these methods only (previous and new certificate links)."""
        methods = methods.exists()
        if not methods:
            return
        pairs = self.with_context(active_test=False).search([("method_id", "in", methods.ids)])
        pairs._recompute_is_accredited()

    @api.constrains("department_id", "subcontractor_id")
    def _check_tester(self):
        for pair in self:
            if pair.department_id and pair.subcontractor_id:
                raise ValidationError(
                    self.env._(
                        "%s is tested either in-house by a department or by a subcontractor, not both.",
                        pair.display_name,
                    )
                )
            if not pair.department_id and not pair.subcontractor_id:
                raise ValidationError(
                    self.env._("%s needs the department that tests it, or a subcontractor.", pair.display_name)
                )

    @api.constrains("subcontractor_id")
    def _check_subcontractor_can_be_chosen(self):
        # Runs when a subcontractor is chosen, so a pair keeps its subcontractor after the accreditation expires.
        for pair in self.filtered("subcontractor_id"):
            subcontractor = pair.subcontractor_id
            if not subcontractor.active:
                raise ValidationError(self.env._("%s is archived and cannot be chosen.", subcontractor.display_name))
            if subcontractor.accreditation_expired:
                raise ValidationError(
                    self.env._(
                        "The accreditation of %(subcontractor)s expired on %(date)s. Renew it before choosing this "
                        "subcontractor.",
                        subcontractor=subcontractor.display_name,
                        date=format_date(self.env, subcontractor.accreditation_expiry),
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "is_accredited" in vals:
                raise UserError(self.env._("Accreditation is computed from certificates; it cannot be set by hand."))
        pairs = super().create(vals_list)
        # The constraint runs only for the fields written, so a create that leaves out both testers would skip it.
        pairs._check_tester()
        return pairs

    def write(self, vals):
        if "is_accredited" in vals:
            raise UserError(self.env._("Accreditation is computed from certificates; it cannot be set by hand."))
        # Removing a line from its parameter, as the parameter's unlink and clear commands do, would delete it.
        if "parameter_id" in vals and not vals["parameter_id"]:
            raise UserError(self._never_deleted_message())
        # Saved from the parameter, another way may become the default in the same save, so the parameter checks it.
        if vals.get("active") is False and self.env.context.get(DEFAULTS_CHECKED_BY_PARAMETER) is not DEFAULTS_CHECKED:
            self._refuse_archiving_defaults()
        result = super().write(vals)
        if "active" in vals:
            # The unique index only counts active ways, so an archived way must be saved before a replacement is; a
            # search through the sample types a parameter is offered on does not recompute them first.
            self.flush_recordset(["active"])
            self.parameter_id.flush_recordset(["sample_type_ids"])
        if vals.get("active") and self.env.context.get(DEFAULTS_CHECKED_BY_PARAMETER) is not DEFAULTS_CHECKED:
            # A restored way never becomes a default, so its sample types must already have another one.
            self.parameter_id._check_defaults(self.applicability_ids.sample_type_id)
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_never(self):
        # Uninstalling a module deletes the ways of testing it shipped, such as demo data. The flag is set for that.
        if not self.env.context.get(MODULE_UNINSTALL_FLAG):
            raise UserError(self._never_deleted_message())

    def _never_deleted_message(self):
        return self.env._(
            "Ways of testing are archived, never deleted: %s. Archive them with their Active toggle instead.",
            format_list(self.env, self.mapped("display_name")),
        )

    def _refuse_archiving_defaults(self):
        defaults = self.applicability_ids.filtered("is_default")
        if defaults:
            raise UserError(
                self.env._(
                    "Choose another default way of testing, or stop offering the parameter on the sample type, before "
                    "archiving the default: %s.",
                    format_list(self.env, defaults.mapped("display_name")),
                )
            )

    def _applicability(self, sample_type):
        """The way's unit, detection limits and decimals on the sample type; empty when it does not apply to it."""
        self.ensure_one()
        return self.applicability_ids.filtered(lambda applicability: applicability.sample_type_id == sample_type)

    def _unavailable_reason(self):
        """Why the way cannot be offered now, or False when it can. Who may test a parameter is not checked yet."""
        self.ensure_one()
        subcontractor = self.subcontractor_id
        if subcontractor and not subcontractor.active:
            return self.env._("%s is archived.", subcontractor.display_name)
        if subcontractor and subcontractor.accreditation_expired:
            return self.env._(
                "The accreditation of %(subcontractor)s expired on %(date)s.",
                subcontractor=subcontractor.display_name,
                date=format_date(self.env, subcontractor.accreditation_expiry),
            )
        links = self.env[MODEL_PARAMETER_METHOD_MACHINE].sudo().search([("parameter_method_id", "=", self.id)])
        now = fields.Datetime.now()
        if links and not any(link.machine_id._usable_until() > now for link in links):
            return self.env._("No machine that runs it is in use with a valid calibration.")
        return False
