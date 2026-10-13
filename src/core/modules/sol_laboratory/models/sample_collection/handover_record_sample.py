from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_HANDOVER_RECORD,
    MODEL_HANDOVER_RECORD_SAMPLE,
    MODEL_PERMISSION_MIXIN,
    MODEL_SAMPLE,
)
from odoo.addons.sol_laboratory.models.sample_collection.sample import CONDITIONS


# Links a handover record to the samples it lists, with the amount and condition handed over.
class HandoverRecordSample(models.Model):
    _name = MODEL_HANDOVER_RECORD_SAMPLE
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Handover Record Sample"
    _order = "id"
    _rec_name = "sample_id"
    # Lines of a draft record can be removed; a signed record keeps them.
    _permission_actions = ("read", "create", "edit", "delete")

    # The handover record.
    record_id = fields.Many2one(MODEL_HANDOVER_RECORD, string="Handover Record", required=True, ondelete="cascade")
    # The sample handed over.
    sample_id = fields.Many2one(MODEL_SAMPLE, required=True, ondelete="restrict", index=True)
    # Amount handed over, such as "2 bottles of 1 L".
    quantity = fields.Char(string="Amount", required=True)
    # Condition as handed over: good, damaged or insufficient.
    condition = fields.Selection(CONDITIONS, required=True)
    # What was wrong with the sample when handed over.
    condition_note = fields.Text(string="Condition Note")

    _record_sample_unique = models.Constraint(
        "UNIQUE(record_id, sample_id)", "This sample is already on the handover record."
    )

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
