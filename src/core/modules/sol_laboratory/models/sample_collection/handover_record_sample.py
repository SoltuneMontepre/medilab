from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_HANDOVER_RECORD,
    MODEL_HANDOVER_RECORD_SAMPLE,
    MODEL_LOCK_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_SAMPLE,
)
from odoo.addons.sol_laboratory.models.sample_collection.sample import CONDITIONS

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_handover_record_sample as HandoverRecordSampleBase
else:
    HandoverRecordSampleBase = object


# Links a handover record to the samples it lists, with what was actually handed over against what was expected.
class HandoverRecordSample(models.Model, HandoverRecordSampleBase):
    _name = MODEL_HANDOVER_RECORD_SAMPLE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Handover Record Sample"
    _order = "id"
    _rec_name = "sample_id"
    # Lines of a draft record can be removed; a signed record keeps them.
    _permission_actions = ("read", "create", "edit", "delete")

    if not TYPE_CHECKING:
        # The handover record.
        record_id = fields.Many2one(MODEL_HANDOVER_RECORD, string="Handover Record", required=True, ondelete="cascade")
        # The sample handed over.
        sample_id = fields.Many2one(MODEL_SAMPLE, required=True, ondelete="restrict", index=True)
        # Physical samples expected for the sample from its sampling requirements; 0 when none were calculated.
        expected_count = fields.Integer(
            string="Expected Samples", compute="_compute_expected_count", store=True, precompute=True
        )
        # Physical samples actually handed over, which the customer confirms by signing; the expected ones to start.
        actual_count = fields.Integer(
            string="Actual Samples",
            compute="_compute_actual_count",
            store=True,
            precompute=True,
            readonly=False,
            required=True,
        )
        # Physical samples handed over beyond the expected ones; they add no test and stay with the sample.
        extra_count = fields.Integer(string="Extra Samples", compute="_compute_differences", store=True)
        # Expected physical samples not handed over; they wait for another collection or Sales cancels them.
        missing_count = fields.Integer(string="Missing Samples", compute="_compute_differences", store=True)
        # Amount handed over, such as "2 bottles of 1 L".
        quantity = fields.Char(string="Amount", required=True)
        # Material handed over beyond what testing needs, such as "300 mL more than required"; it adds no test and
        # stays with the sample.
        excess_material = fields.Char(string="Excess Material")
        # Condition as handed over: good, unusable or insufficient.
        condition = fields.Selection(CONDITIONS, required=True)
        # What was wrong with the sample when handed over.
        condition_note = fields.Text(string="Condition Note")

    _record_sample_unique = models.Constraint(
        "UNIQUE(record_id, sample_id)", "This sample is already on the handover record."
    )
    _actual_count_positive = models.Constraint(
        "CHECK(actual_count > 0)", "Each sample on a handover record needs at least one actual sample."
    )

    @api.depends("sample_id.expected_sampling_ids.objects", "sample_id.expected_sampling_ids.group_number")
    def _compute_expected_count(self):
        for line in self:
            line.expected_count = line.sample_id.sudo().expected_sampling_ids._expected_count()

    # A sample's expected sampling is kept from its accepted quotation and never changes, so a signed line keeps its
    # actual count.
    @api.depends("expected_count")
    def _compute_actual_count(self):
        for line in self:
            line.actual_count = line.expected_count or 1

    @api.depends("expected_count", "actual_count")
    def _compute_differences(self):
        for line in self:
            # A sample with nothing expected has no difference to show.
            expected = line.expected_count or line.actual_count
            line.extra_count = max(line.actual_count - expected, 0)
            line.missing_count = max(expected - line.actual_count, 0)

    @api.model_create_multi
    def create(self, vals_list):
        self._check_draft(self.env[MODEL_HANDOVER_RECORD].browse([vals["record_id"] for vals in vals_list]))
        return super().create(vals_list)

    def write(self, vals):
        self._check_draft(self.record_id)
        return super().write(vals)

    def unlink(self):
        self._check_draft(self.record_id)
        return super().unlink()

    def _check_draft(self, records):
        if any(record.status == "signed" for record in records):
            raise UserError(self.env._("Samples on a signed handover record cannot be changed."))
