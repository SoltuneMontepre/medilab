from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_HANDOVER_RECORD_SAMPLE, MODEL_SAMPLE, MODEL_SAMPLE_RETURN
from odoo.addons.sol_laboratory.constants.xml_ids import (
    HANDOVER_RECORD_SAMPLE_READER_GROUP,
    SAMPLE_RETURN_READER_GROUP,
)
from odoo.addons.sol_laboratory.models.sample_collection.sample_return import EXTRAS, RETAINED, RETURN_KINDS

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample as SampleReturnsBase
else:
    SampleReturnsBase = object


# Mẫu: what the customer handed over of the sample and what the laboratory returns of it.
class SampleReturns(models.Model, SampleReturnsBase):
    _inherit = MODEL_SAMPLE

    if not TYPE_CHECKING:
        # Lines of the handover records that list the sample, with what was actually handed over.
        handover_line_ids = fields.One2many(
            MODEL_HANDOVER_RECORD_SAMPLE,
            "sample_id",
            string="Handover Records",
            groups=HANDOVER_RECORD_SAMPLE_READER_GROUP,
        )
        # What was returned of the sample to the customer.
        return_ids = fields.One2many(
            MODEL_SAMPLE_RETURN, "sample_id", string="Returns", groups=SAMPLE_RETURN_READER_GROUP
        )
        # What the sample can return now: its extra samples and excess material, or itself once retained past its
        # retention period; empty when nothing.
        returnable = fields.Selection(
            RETURN_KINDS,
            string="Can Return",
            compute="_compute_returnable",
        )

    @api.depends(
        "status",
        "retained_until",
        "handover_line_ids.record_id.status",
        "handover_line_ids.extra_count",
        "handover_line_ids.excess_material",
    )
    def _compute_returnable(self):
        for sample in self:
            if sample._retention_over():
                sample.returnable = RETAINED
            elif sample.status not in ("disposed", "returned") and sample._extras_kept():
                sample.returnable = EXTRAS
            else:
                sample.returnable = False

    def _extras_kept(self):
        """True when a signed handover record lists extra samples or excess material of the sample, which testing never
        uses and the sample keeps until the customer asks for them back."""
        self.ensure_one()
        return any(
            line.record_id.status == "signed" and (line.extra_count or line.excess_material)
            for line in self.sudo().handover_line_ids
        )

    def action_open_return(self):
        """Open the return of what the sample can return now, to record what was handed back and to whom."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Return %s", self.code),
            "res_model": MODEL_SAMPLE_RETURN,
            "view_mode": "form",
            "target": "new",
            "context": {"default_sample_id": self.id, "default_kind": self.returnable or EXTRAS},
        }
