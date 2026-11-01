from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE_BOOKING,
    MODEL_PERSON,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SAMPLE_TEST,
)
from odoo.addons.sol_laboratory.models.testing.sample_test import MEASURABLE_STATUSES

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample_test as SampleTestDueDateBase
else:
    SampleTestDueDateBase = object

END_OF_DAY = time(23, 59, 59)
# Fields only the head of department sets, through Change Due Date and Use Automatic Due Date.
DUE_DATE_FIELDS = frozenset({"due_date", "due_date_reason"})


# Chỉ Tiêu Của Mẫu: the sample test's due date.
class SampleTestDueDate(models.Model, SampleTestDueDateBase):
    _inherit = MODEL_SAMPLE_TEST

    if not TYPE_CHECKING:
        # When the laboratory plans to finish the test: the end of the day, in the company's time zone, a safety margin
        # before the request's expected date, worked out again when that date changes, unless the head of department
        # changed it by hand.
        due_date = fields.Datetime(compute="_compute_due_date", store=True, readonly=False)
        # Why the head of department changed the due date by hand; empty while it is worked out from the safety margin.
        due_date_reason = fields.Text(readonly=True, copy=False)
        # True when the due date the head changed is later than the one the request's expected date gives now.
        due_date_conflict = fields.Boolean(compute="_compute_due_date_conflict")
        # True when the company's working calendar has no working time on the day of the due date.
        due_on_non_working_day = fields.Boolean(compute="_compute_due_on_non_working_day")
        # True when the current user heads the department testing the test, until its result is entered.
        can_change_due_date = fields.Boolean(compute="_compute_can_change_due_date")

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            # A new test's due date comes from the safety margin.
            for vals in vals_list:
                for name in DUE_DATE_FIELDS:
                    vals.pop(name, None)
        return super().create(vals_list)

    def write(self, vals):
        if DUE_DATE_FIELDS & set(vals) and not self.env.su:
            raise UserError(self.env._("Change the due date of a sample test with Change Due Date."))
        return super().write(vals)

    @api.depends("sample_id.request_id.expected_date", "due_date_reason")
    def _compute_due_date(self):
        # A due date the head changed stays until the head clears it.
        for test, due_date in self.filtered(lambda test: not test.due_date_reason)._automatic_due_dates().items():
            test.due_date = due_date

    def _automatic_due_dates(self):
        """Each test's due date from the safety margin: the end of the day, in the laboratory's time zone, the margin
        before the request's expected date; False without an expected date."""
        # The margin is read here and is not a dependency: changing it leaves due dates already stored.
        margin = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("safety_margin_days")
        # The laboratory's time zone, so the due date does not depend on who saved the request.
        laboratory_tz = ZoneInfo(self.env.company.tz or "UTC")
        due_dates = {}
        for test in self:
            expected = test.sudo().sample_id.request_id.expected_date
            due_dates[test] = False
            if expected:
                local_end = datetime.combine(expected - timedelta(days=margin), END_OF_DAY, tzinfo=laboratory_tz)
                due_dates[test] = local_end.astimezone(UTC).replace(tzinfo=None)
        return due_dates

    @api.depends("due_date", "due_date_reason", "sample_id.request_id.expected_date")
    def _compute_due_date_conflict(self):
        automatic_due_dates = self._automatic_due_dates()
        for test in self:
            automatic = automatic_due_dates[test]
            test.due_date_conflict = bool(
                test.due_date_reason and test.due_date and automatic and test.due_date > automatic
            )

    @api.depends("due_date")
    def _compute_due_on_non_working_day(self):
        for test in self:
            test.due_on_non_working_day = bool(test.due_date) and not self._is_working_day(test.due_date)

    @api.model
    def _is_working_day(self, moment):
        """True when the company's working calendar has working time on the day of the naive UTC moment, in the
        laboratory's time zone. Company-wide time off counted as working time, such as a public holiday the
        administrator marked as a working day, leaves the day working. The scheduler reads the calendar the same way."""
        zone = ZoneInfo(self.env.company.tz or "UTC")
        day = moment.replace(tzinfo=UTC).astimezone(zone).date()
        start, end = (
            datetime.combine(day + timedelta(days=offset), time.min, tzinfo=zone).astimezone(UTC).replace(tzinfo=None)
            for offset in (0, 1)
        )
        # Without a person, the scheduler gives the company calendar's working time.
        return bool(self.env[MODEL_MACHINE_BOOKING]._working_time(self.env[MODEL_PERSON], start, end))

    @api.depends_context("uid")
    @api.depends("status")
    def _compute_can_change_due_date(self):
        for test in self:
            test.can_change_due_date = (
                test.status in MEASURABLE_STATUSES and self.env.user in test._testing_department().manager_id.user_id
            )

    def _testing_department(self):
        """The department of the test's testing task, or before it has one, of the default way of testing its
        parameter on the sample's type."""
        self.ensure_one()
        test = self.sudo()
        return test._tested_by() or test.sample_id._department_by_test()[test]

    def _change_due_date(self, due_date, reason):
        """The head of the department testing the test changes its due date by hand, with a reason. It stays when the
        request's expected date changes, until the head clears it."""
        self.ensure_one()
        self._check_can_change_due_date()
        if not (reason or "").strip():
            raise UserError(self.env._("Give a reason for changing the due date."))
        self.sudo().write({"due_date": due_date, "due_date_reason": reason})

    def action_clear_due_date(self):
        """The head goes back to the due date worked out from the safety margin."""
        self._check_can_change_due_date()
        # Only a changed due date is worked out again; one set by the system stays.
        self.sudo().filtered("due_date_reason").due_date_reason = False

    def _check_can_change_due_date(self):
        for test in self:
            if not test.can_change_due_date:
                raise UserError(
                    self.env._(
                        "Only the head of the department testing %s changes its due date, until its result is entered.",
                        test.display_name,
                    )
                )
