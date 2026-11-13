from typing import TYPE_CHECKING

from odoo import fields, models
from odoo.tools import format_date

from odoo.addons.sol_laboratory.constants.models import MODEL_TESTING_FIGURE, MODEL_TESTING_FIGURE_PERIOD
from odoo.addons.sol_laboratory.models.testing.testing_figure import PERIOD_FROM, PERIOD_TO

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_testing_figure_period as TestingFigurePeriodBase
else:
    TestingFigurePeriodBase = object


# Kỳ Số Liệu Thử Nghiệm
class TestingFigurePeriod(models.TransientModel, TestingFigurePeriodBase):
    _name = MODEL_TESTING_FIGURE_PERIOD
    _description = "Testing Figures Period"

    if not TYPE_CHECKING:
        # First day of the period.
        date_from = fields.Date(
            string="From", required=True, default=lambda self: self.env[MODEL_TESTING_FIGURE]._period()[0]
        )
        # Last day of the period.
        date_to = fields.Date(
            string="To", required=True, default=lambda self: self.env[MODEL_TESTING_FIGURE]._period()[1]
        )

    _period_check = models.Constraint("CHECK(date_from <= date_to)", "The period must end on or after its first day.")

    def action_show(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("sol_laboratory.action_medilab_testing_figure")
        action["display_name"] = self.env._(
            "Testing Figures %(date_from)s – %(date_to)s",
            date_from=format_date(self.env, self.date_from),
            date_to=format_date(self.env, self.date_to),
        )
        action["context"] = {
            PERIOD_FROM: fields.Date.to_string(self.date_from),
            PERIOD_TO: fields.Date.to_string(self.date_to),
        }
        return action
