from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_HANDOVER_RECORD_SAMPLE

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_handover_record_sample as HandoverRecordSampleMobileBase
else:
    HandoverRecordSampleMobileBase = object


# Links a handover record to the samples it lists: what Medilab Mobile reads of each.
class HandoverRecordSampleMobile(models.Model, HandoverRecordSampleMobileBase):
    _name = MODEL_HANDOVER_RECORD_SAMPLE
    _inherit = MODEL_HANDOVER_RECORD_SAMPLE

    def _mobile_values(self, customer_visible, conditions):
        """The line as the record's screen lists it; the sample is named as the web's form names it."""
        self.ensure_one()
        sample = self.sample_id.sudo()
        return {
            "code": sample.code or "",
            "sample_type": sample.sample_type_id.display_name or "",
            "customer_sample_name": (sample.customer_sample_name or "") if customer_visible else None,
            "expected_count": self.expected_count,
            "actual_count": self.actual_count,
            "quantity": self.quantity,
            "excess_material": self.excess_material or "",
            "condition": conditions.get(self.condition, ""),
            "condition_note": self.condition_note or "",
        }
