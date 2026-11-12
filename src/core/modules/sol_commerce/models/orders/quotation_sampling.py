from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_ORDER_SAMPLE, MODEL_QUOTATION, MODEL_QUOTATION_SAMPLING
from odoo.addons.sol_commerce.services.expected_sampling import sampling_entry
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_SAMPLE_TYPE,
    MODEL_SAMPLING_SNAPSHOT_MIXIN,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_quotation_sampling as QuotationSamplingBase
else:
    QuotationSamplingBase = object


# Nhu Cầu Lấy Mẫu Của Báo Giá
class QuotationSampling(models.Model, QuotationSamplingBase):
    _name = MODEL_QUOTATION_SAMPLING
    _inherit = [MODEL_SAMPLING_SNAPSHOT_MIXIN, MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Quotation Sampling"
    _order = "quotation_id, order_sample_id, group_number, id"
    _permission_actions = ("read",)

    if not TYPE_CHECKING:
        # The quotation that was sent with these sampling needs.
        quotation_id = fields.Many2one(MODEL_QUOTATION, required=True, ondelete="cascade", index=True)
        # The order's sample the needs are for; empty once a revision removed it.
        order_sample_id = fields.Many2one(MODEL_ORDER_SAMPLE, ondelete="set null", index="btree_not_null")
        # The sample type the needs were calculated on.
        sample_type_id = fields.Many2one(MODEL_SAMPLE_TYPE, required=True, ondelete="restrict")

    def _sampling_entries(self):
        """The kept expected samples of each sample, as the expected sampling template shows them."""
        samples = {}
        for row in self:
            samples.setdefault((row.order_sample_id, row.sample_type_id), self.browse())
            samples[row.order_sample_id, row.sample_type_id] |= row
        entries = []
        for (sample, sample_type), rows in samples.items():
            groups = rows.filtered("group_number")
            entries.append(
                sampling_entry(
                    sample,
                    sample_type,
                    max(rows.mapped("objects")),
                    [
                        {
                            "group": row.group_number,
                            "container_type": row.container_type,
                            "preservation": row.preservation,
                            "amount": row.amount,
                            "unit": row.unit_id,
                            "methods": row.method_ids,
                        }
                        for row in groups
                    ],
                    (rows - groups).method_ids,
                )
            )
        return entries
