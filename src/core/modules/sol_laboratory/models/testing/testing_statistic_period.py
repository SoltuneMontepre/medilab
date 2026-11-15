from typing import TYPE_CHECKING

from odoo import fields, models
from odoo.tools import format_date

from odoo.addons.sol_laboratory.constants.models import MODEL_TESTING_STATISTIC, MODEL_TESTING_STATISTIC_PERIOD
from odoo.addons.sol_laboratory.constants.statistics import STATISTICS_FROM, STATISTICS_TO

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_testing_statistic_period as TestingStatisticPeriodBase
else:
    TestingStatisticPeriodBase = object


# Kỳ Thống Kê Thử Nghiệm
class TestingStatisticPeriod(models.TransientModel, TestingStatisticPeriodBase):
    _name = MODEL_TESTING_STATISTIC_PERIOD
    _description = "Testing Statistics Period"

    if not TYPE_CHECKING:
        # First day of the period.
        date_from = fields.Date(
            string="From", required=True, default=lambda self: self.env[MODEL_TESTING_STATISTIC]._period()[0]
        )
        # Last day of the period.
        date_to = fields.Date(
            string="To", required=True, default=lambda self: self.env[MODEL_TESTING_STATISTIC]._period()[1]
        )

    _period_check = models.Constraint("CHECK(date_from <= date_to)", "The period must end on or after its first day.")

    def action_show(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("sol_laboratory.action_medilab_testing_statistic")
        action["display_name"] = self.env._(
            "Testing Statistics %(date_from)s – %(date_to)s",
            date_from=format_date(self.env, self.date_from),
            date_to=format_date(self.env, self.date_to),
        )
        action["context"] = {
            STATISTICS_FROM: fields.Date.to_string(self.date_from),
            STATISTICS_TO: fields.Date.to_string(self.date_to),
        }
        return action
