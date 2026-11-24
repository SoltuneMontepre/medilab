from typing import TYPE_CHECKING

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.tools.misc import format_date

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderReturnTimelineBase
else:
    SaleOrderReturnTimelineBase = object


# Đơn Hàng: how the expected return date is reached, step by step, while Sales prepares the quotation.
class SaleOrderReturnTimeline(models.Model, SaleOrderReturnTimelineBase):
    _inherit = MODEL_SALE_ORDER

    if not TYPE_CHECKING:
        # The steps from the sample pickup to the expected return date, shown under the date before sending.
        return_timeline = fields.Html(compute="_compute_return_timeline", sanitize=False)

    @api.depends(
        "expected_collection_date", "turnaround_days", "order_line.parameter_method_id", "committed_date", "state"
    )
    def _compute_return_timeline(self):
        for order in self:
            estimate = order.state != "cancel" and order._return_estimate()
            order.return_timeline = order._render_return_timeline(estimate) if estimate and estimate["date"] else False

    def _render_return_timeline(self, estimate):
        self.ensure_one()
        _ = self.env._

        def day(value):
            return format_date(self.env, value, date_format="EEE dd/MM")

        steps = [
            (
                _("Sample pickup") if self.expected_collection_date else _("Samples received from"),
                day(estimate["start"]),
                "",
            )
        ]
        if estimate.get("testing"):
            steps.append((_("Testing finishes"), day(estimate["testing"]), _("on the laboratory's schedule")))
            if estimate.get("margin"):
                steps.append(
                    (
                        _("Safety margin"),
                        _("+%s working days", estimate["margin"]),
                        _("for approval and signing"),
                    )
                )
        if estimate.get("turnaround"):
            steps.append(
                (
                    _("Standard turnaround"),
                    day(estimate["turnaround"]),
                    "",
                )
            )
        expected = self.committed_date or estimate["date"]
        cells = Markup("").join(
            Markup(
                '<li class="o_medilab_timeline_step"><span class="text-muted small">%s</span><span>%s</span>'
                '<span class="text-muted small">%s</span></li>'
            )
            % (label, value, hint)
            for label, value, hint in steps
        )
        result = Markup(
            '<li class="o_medilab_timeline_step o_medilab_timeline_step_final"><span class="text-muted small">%s</span>'
            "<strong>%s</strong></li>"
        ) % (_("Expected return"), day(expected))
        requested = Markup("")
        if self.requested_date:
            met = self.requested_date >= expected
            requested = Markup('<p class="mb-0 mt-2 small %s">%s</p>') % (
                "text-success" if met else "text-warning",
                _("Customer asked for %s.", escape(day(self.requested_date))),
            )
        return Markup('<ol class="o_medilab_return_timeline">%s%s</ol>%s') % (cells, result, requested)
