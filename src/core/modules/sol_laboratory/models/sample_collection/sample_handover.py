from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_list

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DEPARTMENT,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_SAMPLE,
    MODEL_SAMPLE_HANDOVER,
)


# Bàn Giao Mẫu
class SampleHandover(models.Model):
    _name = MODEL_SAMPLE_HANDOVER
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Sample Handover"
    _order = "id desc"
    _rec_name = "sample_id"
    _permission_actions = ("read", "create", "edit")

    # The sample handed over.
    sample_id = fields.Many2one(MODEL_SAMPLE, required=True, ondelete="cascade")
    # The department that receives it.
    department_id = fields.Many2one(MODEL_DEPARTMENT, required=True, ondelete="restrict")
    # When the department received it; empty while it is on its way.
    received_at = fields.Datetime(readonly=True, copy=False)
    # Person in the department who received it.
    received_by_id = fields.Many2one(MODEL_PERSON, string="Received By", readonly=True, copy=False, ondelete="restrict")

    _sample_department_unique = models.Constraint(
        "UNIQUE(sample_id, department_id)", "This sample is already handed over to this department."
    )
    _department_received_idx = models.Index("(department_id, received_at)")

    @api.model_create_multi
    def create(self, vals_list):
        samples = self.env[MODEL_SAMPLE].browse([vals["sample_id"] for vals in vals_list])
        blocked = samples.filtered(lambda sample: sample.status != "received")
        if blocked:
            raise UserError(
                self.env._(
                    "Only a received sample can be handed over to a department. Not received: %s",
                    format_list(self.env, blocked.mapped("code")),
                )
            )
        return super().create(vals_list)

    @api.model
    def receive_by_label(self, code):
        sample = self.env[MODEL_SAMPLE].search([("code", "=", code)], limit=1)
        if not sample:
            raise UserError(self.env._("No sample has the lab code %s.", code))
        person = self.env[MODEL_PERSON]._current()
        if not person or not person.department_id:
            raise UserError(self.env._("You are not in a department that receives samples."))
        handover = self.search(
            [("sample_id", "=", sample.id), ("department_id", "=", person.department_id.id)], limit=1
        )
        if not handover:
            raise UserError(self.env._("%s has no handover to %s.", sample.code, person.department_id.name))
        # Scanning a label again keeps the first receipt.
        if not handover.received_at:
            handover.write({"received_at": fields.Datetime.now(), "received_by_id": person.id})
        return handover
