from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_SAMPLE,
    MODEL_SAMPLE_RETURN,
    MODEL_TASK,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample_return as SampleReturnBase
else:
    SampleReturnBase = object

EXTRAS = "extras"
RETAINED = "retained"
# What a sample can return: its extra samples and excess material, or itself once retained past its retention period.
RETURN_KINDS = [(EXTRAS, "Extra Samples and Excess Material"), (RETAINED, "Retained Sample")]


# Trả Mẫu
class SampleReturn(models.Model, SampleReturnBase):
    _name = MODEL_SAMPLE_RETURN
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Sample Return"
    _order = "returned_at desc, id desc"
    _rec_name = "sample_id"
    # A return records what was handed back; it is never changed or deleted.
    _permission_actions = ("read", "create")

    if not TYPE_CHECKING:
        # The sample whose material is returned.
        sample_id = fields.Many2one(MODEL_SAMPLE, required=True, ondelete="restrict", index=True)
        # What is returned: the extra samples and excess material testing never uses, or the retained sample once its
        # retention period is over.
        kind = fields.Selection(
            RETURN_KINDS,
            string="Returned",
            required=True,
            default=EXTRAS,
        )
        # What was handed back, such as "1 extra 500 mL bottle and 300 mL of excess material".
        description = fields.Text(string="What Was Returned", required=True)
        # When it was handed back.
        returned_at = fields.Datetime(required=True, readonly=True, default=fields.Datetime.now)
        # Person who handed it back.
        returned_by_id = fields.Many2one(
            MODEL_PERSON, string="Returned By", required=True, readonly=True, ondelete="restrict"
        )
        # Name of the customer's person who took it, such as at the counter when collecting the report.
        returned_to_name = fields.Char(string="Returned To", required=True)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            person = self.env[MODEL_PERSON]._current()
            if not person:
                raise UserError(self.env._("Only a person can return a sample."))
            for vals in vals_list:
                vals.update(returned_by_id=person.id, returned_at=fields.Datetime.now())
        returns = super().create(vals_list)
        returns._check_returnable()
        # Returning is the permission that matters; the retained sample ends as returned with full rights.
        retained = returns.filtered(lambda record: record.kind == RETAINED).sample_id.sudo()
        retained.write({"status": "returned"})
        self.env[MODEL_TASK]._cancel_for_document(retained, "dispose")
        return returns

    def _check_returnable(self):
        for record in self:
            sample = record.sample_id.sudo()
            if record.kind == RETAINED:
                # A sample is returned once, also when one batch returns it twice.
                twice = self.filtered(lambda other: other.kind == RETAINED and other.sample_id == record.sample_id)
                if len(twice) > 1 or not sample._retention_over():
                    raise UserError(
                        self.env._(
                            "A retained sample is returned only once its retention period is over: %s", sample.code
                        )
                    )
            elif sample.status in ("disposed", "returned"):
                raise UserError(
                    self.env._("Sample %s is no longer kept, so nothing of it can be returned.", sample.code)
                )
            elif not sample._extras_kept():
                raise UserError(self.env._("Sample %s keeps no extra samples or excess material.", sample.code))
