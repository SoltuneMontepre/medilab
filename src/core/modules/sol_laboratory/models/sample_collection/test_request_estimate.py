from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE_BOOKING,
    MODEL_MACHINE_METHOD,
    MODEL_PARAMETER_AUTHORIZATION,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.models.sample_collection.committed_date_change import CHANGING_COMMITTED_DATE
from odoo.addons.sol_laboratory.models.testing.machine_booking import HORIZON_DAYS, _slot_length

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_request as TestRequestEstimateBase
else:
    TestRequestEstimateBase = object

UTC = ZoneInfo("UTC")


# Yêu Cầu Thử Nghiệm: the standard turnaround of its ways of testing, and the feasibility check of a priority date.
class TestRequestEstimate(models.Model, TestRequestEstimateBase):
    _inherit = MODEL_TEST_REQUEST

    @api.model
    def _turnaround(self, ways):
        """The working days results take from sample receipt: the longest standard turnaround of the ways. Returns the
        days, or 0 with the ways that have no turnaround yet."""
        ways = ways.sudo()
        missing = ways.filtered(lambda way: not way.turnaround_days)
        if missing or not ways:
            return {"days": 0, "missing": missing}
        return {"days": max(ways.mapped("turnaround_days")), "missing": missing}

    @api.model
    def _date_after_working_days(self, day, days):
        """The day the company's working calendar reaches the given working days after the day."""
        calendar = self.env.company.resource_calendar_id
        zone = ZoneInfo(self.env.company.tz or "UTC")
        start = datetime.combine(day, time(23, 59), tzinfo=zone)
        planned = calendar.plan_days(days, start, compute_leaves=True)
        return planned.astimezone(zone).date() if isinstance(planned, datetime) else day + timedelta(days=days)

    @api.model
    def _check_priority(self, ways, requested_date):
        """Whether testing by the ways can return results by the requested date. The check only reads: it simulates
        each in-house way on the people authorized for its parameter in its department and the machines of its method,
        and counts a subcontracted way's turnaround from today. The latest finish plus the safety margin is the earliest
        feasible date. Returns that date, or False with the reasons it cannot be given."""
        now = fields.Datetime.now()
        zone = ZoneInfo(self.env.company.tz or "UTC")
        today = now.replace(tzinfo=UTC).astimezone(zone).date()
        finishes, reasons = [], []
        for way in ways.sudo():
            if way.subcontractor_id:
                if not way.turnaround_days:
                    reasons.append(self.env._("%s has no turnaround.", way.display_name))
                    continue
                finishes.append(self._date_after_working_days(today, way.turnaround_days))
                continue
            finish = self._earliest_in_house_finish(way, now)
            if not finish:
                reasons.append(
                    self.env._(
                        "No authorized person and machine has a free slot for %(way)s in the next %(days)s days.",
                        way=way.display_name,
                        days=HORIZON_DAYS,
                    )
                )
                continue
            finishes.append(finish.replace(tzinfo=UTC).astimezone(zone).date())
        if reasons or not finishes:
            return {"date": False, "feasible": False, "reasons": reasons}
        margin = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("safety_margin_days")
        earliest = max(finishes) + timedelta(days=margin)
        return {"date": earliest, "feasible": bool(requested_date) and earliest <= requested_date, "reasons": []}

    @api.model
    def _earliest_in_house_finish(self, way, now):
        # The earliest end of a free slot for the way, among its parameter's authorized people in its department and
        # the machines of its method, or without a machine for the way's own duration; None when there is none.
        bookings = self.env[MODEL_MACHINE_BOOKING]
        people = (
            self.env[MODEL_PARAMETER_AUTHORIZATION]
            .sudo()
            .search([("parameter_id", "=", way.parameter_id.id)])
            .person_id.filtered(lambda person: person.department_id == way.department_id)
        )
        links = self.env[MODEL_MACHINE_METHOD].sudo().search([("method_id", "=", way.method_id.id)])
        options = [(link.machine_id, link.duration_minutes) for link in links]
        if not links and way.duration_minutes:
            options.append((links.machine_id.browse(), way.duration_minutes))
        not_after = now + timedelta(days=HORIZON_DAYS)
        rooms = bookings._room_steps(way)
        best = None
        for person in people:
            for machine, minutes in options:
                length = _slot_length(minutes)
                start = bookings._free_slot(machine, length, person, not_after, rooms=rooms, way=way)
                if start and (best is None or start + length < best):
                    best = start + length
        return best

    def _commit_on_receipt(self):
        """Fix the committed return date of requests that have none when their first sample is received: the receipt
        day plus the request's turnaround in working days."""
        zone = ZoneInfo(self.env.company.tz or "UTC")
        today = fields.Datetime.now().replace(tzinfo=UTC).astimezone(zone).date()
        for request in self.sudo().filtered(
            lambda request: bool(not request.committed_date and request.turnaround_days)
        ):
            request.with_context(**{CHANGING_COMMITTED_DATE: True}).committed_date = self._date_after_working_days(
                today, request.turnaround_days
            )
