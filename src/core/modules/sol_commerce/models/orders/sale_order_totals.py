from odoo import api, models

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER

# The label Odoo's Sales gives the discount total under the order totals.
ADVANTAGE_LABEL = "Total Advantage"


# Đơn Hàng: the totals shown under the order lines.
class SaleOrderTotals(models.Model):
    _inherit = MODEL_SALE_ORDER

    @api.depends_context("lang")
    def _compute_extra_total_fields(self):
        """Odoo's Vietnamese leaves the discount total untranslated, so this module translates it."""
        result = super()._compute_extra_total_fields()
        label = self.env._("Total Advantage")
        for order in self:
            groups = order.extra_total_fields or []
            if not any(line.get("label") == ADVANTAGE_LABEL for group in groups for line in group.get("lines", [])):
                continue
            order.extra_total_fields = [
                {
                    **group,
                    "lines": [
                        {**line, "label": label} if line.get("label") == ADVANTAGE_LABEL else line
                        for line in group.get("lines", [])
                    ],
                }
                for group in groups
            ]
        return result
