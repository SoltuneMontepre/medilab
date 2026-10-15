from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import format_date

from odoo.addons.sol_laboratory.constants.departments import DEPARTMENT_DOMAIN
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_DEPARTMENT,
    MODEL_MEASUREMENT_UNIT,
    MODEL_PARAMETER_METHOD,
    MODEL_PERMISSION_MIXIN,
    MODEL_SUBCONTRACTOR,
    MODEL_TEST_PARAMETER,
    MODEL_TESTING_METHOD,
)


# Cách Thử
class ParameterMethod(models.Model):
    _name = MODEL_PARAMETER_METHOD
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Way of Testing"
    _order = "parameter_id, is_default desc, id"
    _rec_names_search = ("parameter_id", "method_id")
    _permission_actions = ("create", "edit", "archive", "delete")

    # The parameter being tested.
    parameter_id = fields.Many2one(MODEL_TEST_PARAMETER, required=True, ondelete="restrict")
    # The method used to test it.
    method_id = fields.Many2one(
        MODEL_TESTING_METHOD, required=True, ondelete="restrict", index=True, string="Testing Method"
    )
    # The unit the result is expressed in.
    unit_id = fields.Many2one(MODEL_MEASUREMENT_UNIT, required=True, ondelete="restrict", index=True)
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
    # True when this way of testing is within an ISO 17025 accreditation scope.
    is_accredited = fields.Boolean(string="Accredited")
    # Limit of detection: the lowest value this method can detect, in the row's unit.
    lod = fields.Float(string="LOD", digits=0)
    # Limit of quantification: the lowest value this method can measure reliably, in the row's unit.
    loq = fields.Float(string="LOQ", digits=0)
    # Decimals a result of this way of testing shows, such as 2 for 0.50; results copy it.
    result_decimals = fields.Integer()
    # True for the way the parameter is normally tested.
    is_default = fields.Boolean(string="Default")
    # False when this way of testing is archived.
    active = fields.Boolean(default=True)

    _parameter_method_unique = models.UniqueIndex(
        "(parameter_id, method_id, COALESCE(subcontractor_id, 0)) WHERE active",
        "The parameter is already tested with this method by the same laboratory.",
    )
    _one_default = models.UniqueIndex(
        "(parameter_id) WHERE is_default", "A test parameter has only one default way of testing."
    )

    @api.depends("parameter_id", "method_id", "subcontractor_id")
    def _compute_display_name(self):
        for pair in self:
            name = f"{pair.parameter_id.name} – {pair.method_id.code}"
            pair.display_name = f"{name} ({pair.subcontractor_id.name})" if pair.subcontractor_id else name

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
        self._unset_defaults([vals.get("parameter_id") for vals in vals_list if vals.get("is_default")])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("is_default"):
            self._unset_defaults([vals["parameter_id"]] if vals.get("parameter_id") else self.parameter_id.ids)
        # Archiving drops the default so another way of testing can take it. Done with full rights so archive
        # alone is enough; the permission check would otherwise also demand edit.
        if vals.get("active") is False and not vals.get("is_default"):
            self.filtered("is_default").sudo().write({"is_default": False})
        return super().write(vals)

    def _unset_defaults(self, parameter_ids):
        # Making a way of testing the default replaces the parameter's previous default. The change is flushed
        # at once so the unique index never sees two defaults in one statement.
        previous = (
            self.with_context(active_test=False).search(
                [("parameter_id", "in", parameter_ids), ("is_default", "=", True)]
            )
            - self
        )
        previous.is_default = False
        previous.flush_recordset(["is_default"])
