from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_MEASUREMENT_UNIT,
    MODEL_PERMISSION_MIXIN,
    MODEL_SAMPLE_TYPE,
    MODEL_SAMPLING_REQUIREMENT,
    MODEL_TESTING_METHOD,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sampling_requirement as SamplingRequirementBase
else:
    SamplingRequirementBase = object

# Container types and preservation conditions are compared in this language, so their translations do not split a
# sampling group.
GROUPING_LANGUAGE = "en_US"


# Yêu Cầu Lấy Mẫu
class SamplingRequirement(models.Model, SamplingRequirementBase):
    _name = MODEL_SAMPLING_REQUIREMENT
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Sampling Requirement"
    _order = "method_id, sample_type_id, id"
    _permission_actions = ("create", "edit", "delete")

    if not TYPE_CHECKING:
        # The testing method that needs the sample.
        method_id = fields.Many2one(
            MODEL_TESTING_METHOD, string="Testing Method", required=True, ondelete="cascade", index=True
        )
        # The sample type the requirement applies to; its narrower and broader types do not share it.
        sample_type_id = fields.Many2one(MODEL_SAMPLE_TYPE, required=True, ondelete="restrict", index=True)
        # Amount of sample the method needs, in the unit.
        amount = fields.Float(required=True, digits=0)
        # Unit of the amount, such as mL or g.
        unit_id = fields.Many2one(MODEL_MEASUREMENT_UNIT, string="Unit", required=True, ondelete="restrict", index=True)
        # Container the sample is collected in, such as "Sterile glass bottle", in each language.
        container_type = fields.Char(string="Container", required=True, translate=True)
        # How the sample is preserved until testing, such as "Chilled at 2-8 °C", in each language.
        preservation = fields.Char(required=True, translate=True)

    _method_sample_type_unique = models.Constraint(
        "UNIQUE(method_id, sample_type_id)", "A testing method has only one sampling requirement for each sample type."
    )
    _amount_positive = models.Constraint("CHECK(amount > 0)", "The amount of a sampling requirement must be above 0.")

    @api.depends("method_id", "sample_type_id")
    def _compute_display_name(self):
        for requirement in self:
            requirement.display_name = f"{requirement.method_id.code} – {requirement.sample_type_id.name}"

    def _group_key(self):
        """Requirements with the same container type and preservation condition are one sampling group."""
        self.ensure_one()
        source = self.with_context(lang=GROUPING_LANGUAGE)
        return (
            " ".join((source.container_type or "").split()).casefold(),
            " ".join((source.preservation or "").split()).casefold(),
        )

    @api.model
    def _sampling_rows(self, sample_type, methods):
        """The sampling groups the methods need on the sample type, and the methods that state no requirement for it.

        Each row is one group and one unit: the amounts of a group's methods add when they share a unit; amounts in
        another unit are a row of their own in the same group, never converted. Rows are numbered by their group.
        """
        requirements = self.search(
            Domain("sample_type_id", "=", sample_type.id) & Domain("method_id", "in", methods.ids)
        )
        groups = {}
        for requirement in requirements:
            units = groups.setdefault(requirement._group_key(), {})
            units.setdefault(requirement.unit_id, self.browse())
            units[requirement.unit_id] |= requirement
        rows = []
        for number, units in enumerate(groups.values(), start=1):
            for unit, unit_requirements in units.items():
                rows.append(
                    {
                        "group": number,
                        "requirements": unit_requirements,
                        "amount": sum(unit_requirements.mapped("amount")),
                        "unit": unit,
                        "methods": unit_requirements.method_id,
                    }
                )
        return rows, methods - requirements.method_id
