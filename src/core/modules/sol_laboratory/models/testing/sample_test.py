from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_PERMISSION_MIXIN,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SAMPLE,
    MODEL_SAMPLE_TEST,
    MODEL_TEST_PARAMETER,
)

CANCELLABLE_STATUSES = ("waiting", "assigned", "testing")
FINISHED_STATUSES = ("approved", "cancelled")
END_OF_DAY = time(23, 59, 59)


# Chỉ Tiêu Của Mẫu
class SampleTest(models.Model):
    _name = MODEL_SAMPLE_TEST
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Sample Test"
    _order = "sample_id, id"
    _rec_name = "parameter_id"
    # A sample test is cancelled, never archived or deleted.
    _permission_actions = ("read", "create", "edit")

    # The sample tested.
    sample_id = fields.Many2one(MODEL_SAMPLE, required=True, ondelete="cascade", index=True)
    # The parameter tested.
    parameter_id = fields.Many2one(MODEL_TEST_PARAMETER, required=True, ondelete="restrict", index=True)
    # How many times the parameter is tested on the sample; at least 1.
    quantity = fields.Integer(required=True, default=1)
    # Where the test is in its lifecycle.
    status = fields.Selection(
        [
            ("waiting", "Waiting"),
            ("assigned", "Assigned"),
            ("testing", "Testing"),
            ("outsourced", "Outsourced"),
            ("result_entered", "Result Entered"),
            ("approved", "Approved"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="waiting",
        readonly=True,
        copy=False,
        index=True,
    )
    # When the laboratory plans to finish the test. The default is the end of the day, in the company's time zone, a
    # safety margin before the request's expected date; it can be changed, and is worked out again when that date changes.
    due_date = fields.Datetime(compute="_compute_due_date", store=True, readonly=False)

    _quantity_positive = models.Constraint("CHECK(quantity >= 1)", "A parameter is tested at least once on a sample.")

    @api.depends("sample_id.request_id.expected_date")
    def _compute_due_date(self):
        # The margin is read here and is not a dependency: changing it leaves due dates already stored.
        margin = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("safety_margin_days")
        # The laboratory's time zone, so the due date does not depend on who saved the request.
        laboratory_tz = ZoneInfo(self.env.company.tz or "UTC")
        for test in self:
            expected = test.sample_id.request_id.expected_date
            if not expected:
                test.due_date = False
                continue
            local_end = datetime.combine(expected - timedelta(days=margin), END_OF_DAY, tzinfo=laboratory_tz)
            test.due_date = local_end.astimezone(UTC).replace(tzinfo=None)

    def _cancel(self):
        self.filtered(lambda test: test.status in CANCELLABLE_STATUSES).status = "cancelled"

    def _in_use_domain(self):
        return Domain("status", "not in", FINISHED_STATUSES)
