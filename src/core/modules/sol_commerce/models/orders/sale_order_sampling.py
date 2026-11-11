from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_QUOTATION_SAMPLING, MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import QUOTATION_REPLACED
from odoo.addons.sol_commerce.constants.xml_ids import EXPECTED_SAMPLING_TEMPLATE
from odoo.addons.sol_commerce.services.expected_sampling import sampling_entry
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLING_REQUIREMENT, MODEL_TESTING_METHOD

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderSamplingBase
else:
    SaleOrderSamplingBase = object


# Đơn Hàng: the expected samples, containers and amounts of the order, from its methods' sampling requirements.
class SaleOrderSampling(models.Model, SaleOrderSamplingBase):
    _inherit = MODEL_SALE_ORDER

    if not TYPE_CHECKING:
        # The expected samples, containers and amounts shown to sales and the customer before sending.
        expected_sampling_html = fields.Html(
            string="Expected Samples", compute="_compute_expected_sampling_html", sanitize=False
        )

    @api.depends(
        "state",
        "quotation_ids.status",
        "order_line.product_uom_qty",
        "order_line.sample_id",
        "order_line.sample_type_id",
        "order_line.parameter_method_id",
    )
    def _compute_expected_sampling_html(self):
        for order in self:
            order.expected_sampling_html = self.env["ir.qweb"]._render(
                EXPECTED_SAMPLING_TEMPLATE, {"entries": order._expected_sampling()}
            )

    def _sampling_quotation(self):
        """The quotation whose kept sampling the order follows: the latest one sent, until a revision starts."""
        self.ensure_one()
        latest = self._latest_quotation()
        if latest and self.state != "draft" and latest.status != QUOTATION_REPLACED:
            return latest
        return latest.browse()

    def _sampling_inputs(self):
        """What the sampling of each sample is calculated from: its order sample, or its sample type for lines not on a
        sample yet, the objects and the testing methods of the ways chosen, a package's parameters included.

        The objects are the largest quantity of the lines the customer ordered for the sample.
        """
        self.ensure_one()
        inputs = {}
        for line in self.order_line._way_lines().filtered("sample_type_id"):
            key = line.sample_id or line.sample_type_id
            ordered = line.linked_line_id or line
            entry = inputs.setdefault(
                key,
                {
                    "sample": line.sample_id,
                    "sample_type": line.sample_type_id,
                    "objects": 0,
                    "methods": self.env[MODEL_TESTING_METHOD],
                },
            )
            entry["objects"] = max(entry["objects"], int(ordered.product_uom_qty))
            entry["methods"] |= line.parameter_method_id.sudo().method_id
        return list(inputs.values())

    def _expected_sampling(self):
        """The expected samples of each sample of the order, as kept with its quotation or calculated now."""
        self.ensure_one()
        quotation = self._sampling_quotation()
        if quotation:
            return quotation.sampling_ids._sampling_entries()
        requirements = self.env[MODEL_SAMPLING_REQUIREMENT].sudo()
        entries = []
        for item in self._sampling_inputs():
            rows, missing = requirements._sampling_rows(item["sample_type"], item["methods"])
            groups = [
                {
                    "group": row["group"],
                    "container_type": row["requirements"][:1].container_type,
                    "preservation": row["requirements"][:1].preservation,
                    "amount": row["amount"],
                    "unit": row["unit"],
                    "methods": row["methods"],
                }
                for row in rows
            ]
            entries.append(sampling_entry(item["sample"], item["sample_type"], item["objects"], groups, missing))
        return entries

    def _keep_sampling(self, quotation):
        """Keep the order's sampling with the quotation sent, so later catalog changes do not rewrite it."""
        self.ensure_one()
        requirements = self.env[MODEL_SAMPLING_REQUIREMENT].sudo()
        snapshots = self.env[MODEL_QUOTATION_SAMPLING].sudo()
        for item in self._sampling_inputs():
            rows, missing = requirements._sampling_rows(item["sample_type"], item["methods"])
            snapshots._create_rows(
                {
                    "quotation_id": quotation.id,
                    "order_sample_id": item["sample"].id,
                    "sample_type_id": item["sample_type"].id,
                },
                rows,
                missing,
                item["objects"],
            )
