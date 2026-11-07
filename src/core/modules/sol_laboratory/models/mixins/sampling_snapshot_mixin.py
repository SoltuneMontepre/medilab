from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MEASUREMENT_UNIT,
    MODEL_RES_LANG,
    MODEL_SAMPLING_SNAPSHOT_MIXIN,
    MODEL_TESTING_METHOD,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sampling_snapshot_mixin as SamplingSnapshotMixinBase
else:
    SamplingSnapshotMixinBase = object

TRANSLATED_FIELDS = ("container_type", "preservation")


# Kept copy of the sampling needs of one sample, so later catalog changes do not rewrite it.
class SamplingSnapshotMixin(models.AbstractModel, SamplingSnapshotMixinBase):
    _name = MODEL_SAMPLING_SNAPSHOT_MIXIN
    _description = "Sampling Snapshot"
    _order = "group_number, id"

    if not TYPE_CHECKING:
        # Number of objects of the sample: the largest quantity of the lines tested on it.
        objects = fields.Integer(required=True, default=1)
        # Which sampling group the row belongs to, from 1; 0 for the methods that state no sampling requirement.
        group_number = fields.Integer(string="Group", required=True, default=0)
        # Container of the group, as the requirements stated it, in each language; empty without a requirement.
        container_type = fields.Char(string="Container", translate=True)
        # Preservation condition of the group, as the requirements stated it, in each language; empty without a
        # requirement.
        preservation = fields.Char(translate=True)
        # Amount the group's methods need together in the unit, for each object.
        amount = fields.Float(digits=0)
        # Unit of the amount; empty without a requirement.
        unit_id = fields.Many2one(MODEL_MEASUREMENT_UNIT, string="Unit", ondelete="restrict")
        # The testing methods whose requirements the row adds, or that state none.
        method_ids = fields.Many2many(MODEL_TESTING_METHOD, string="Testing Methods")

    @api.model
    def _create_rows(self, values, rows, missing, objects):
        """Keep the calculated sampling rows of one sample, with the values given, and the methods without a
        requirement as a row of group 0."""
        vals_list = [
            {
                **values,
                "objects": objects,
                "group_number": row["group"],
                "container_type": row["requirements"][:1].container_type,
                "preservation": row["requirements"][:1].preservation,
                "amount": row["amount"],
                "unit_id": row["unit"].id,
                "method_ids": row["methods"].ids,
            }
            for row in rows
        ]
        if missing:
            vals_list.append({**values, "objects": objects, "group_number": 0, "method_ids": missing.ids})
        created = self.create(vals_list)
        for record, row in zip(created, rows, strict=False):
            record._copy_translations(row["requirements"][:1])
        return created

    def _copy_to(self, model, values):
        """Copy the rows onto another sampling snapshot model, with the values given."""
        copies = self.env[model]
        for row in self:
            copy = self.env[model].create(
                {
                    **values,
                    "objects": row.objects,
                    "group_number": row.group_number,
                    "container_type": row.container_type,
                    "preservation": row.preservation,
                    "amount": row.amount,
                    "unit_id": row.unit_id.id,
                    "method_ids": row.method_ids.ids,
                }
            )
            copy._copy_translations(row)
            copies |= copy
        return copies

    def _copy_translations(self, source):
        self.ensure_one()
        if not source:
            return
        languages = [code for code, _name in self.env[MODEL_RES_LANG].get_installed()]
        for field_name in TRANSLATED_FIELDS:
            translations = {code: source.with_context(lang=code)[field_name] for code in languages}
            self.update_field_translations(field_name, {code: value for code, value in translations.items() if value})

    def _expected_count(self):
        """Expected samples of one sample's rows: its objects times its sampling groups."""
        groups = {row.group_number for row in self if row.group_number}
        return max(self.mapped("objects"), default=0) * len(groups)
