from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SAMPLE_TEST,
    MODEL_TASK,
    MODEL_TASK_TYPE,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_COLLECTION_CODE
from odoo.addons.sol_laboratory.models.sample_collection.committed_date_change import CHANGING_COMMITTED_DATE
from odoo.addons.sol_laboratory.models.testing.machine_booking import HORIZON_DAYS

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_request as TestRequestEstimateBase
else:
    TestRequestEstimateBase = object

UTC = ZoneInfo("UTC")


# Yêu Cầu Thử Nghiệm: what happens to its dates and collection: the standard turnaround of its ways of testing, the
# earliest return date the laboratory's held work allows, the feasibility check of a priority date, and the committed
# date and collection tasks settled at sample receipt.
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
    def _working_days_before(self, day, days):
        """The day the given working days before the day, counting only the days of the company's working calendar."""
        tests = self.env[MODEL_SAMPLE_TEST]
        found, tries = 0, 0
        while found < days and tries < 366:
            day -= timedelta(days=1)
            tries += 1
            if tests._is_working_day(tests._end_of_day(day)):
                found += 1
        return day

    @api.model
    def _earliest_return(self, ways, start, turnaround_days, urgent=False, exclude=None, strict=False):
        """The earliest return date of a test for each way in the list when the samples arrive at start: the standard
        turnaround from that day, or later when the laboratory's held work leaves the last test to finish later, plus
        the safety margin in working days. A way no free slot is found for counts by the turnaround alone, unless
        strict, when the date cannot be given. Returns the date, or False with the reasons it cannot be given, and its
        parts: the day the last test finishes, the safety margin in working days and the turnaround's date."""
        simulated = self._simulate_ways(ways, start, urgent=urgent, exclude=exclude)
        if strict and simulated["missing"]:
            return {
                "date": False,
                "reasons": [
                    self.env._(
                        "No authorized person and machine has a free slot for %(way)s in the next %(days)s days.",
                        way=way.display_name,
                        days=HORIZON_DAYS,
                    )
                    for way in simulated["missing"]
                ],
            }
        tests = self.env[MODEL_SAMPLE_TEST]
        days = [simulated["returned"]] if simulated["returned"] else []
        if simulated["finish"]:
            days.append(tests._local_day(simulated["finish"]))
        margin = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("safety_margin_days")
        candidates = [self._date_after_working_days(max(days), margin) if margin else max(days)] if days else []
        turnaround = turnaround_days and self._date_after_working_days(tests._local_day(start), turnaround_days)
        if turnaround:
            candidates.append(turnaround)
        return {
            "date": max(candidates) if candidates else False,
            "reasons": [],
            "testing": max(days) if days else False,
            "margin": margin,
            "turnaround": turnaround or False,
        }

    @api.model
    def _check_priority(self, ways, requested_date):
        """Whether testing a test for each way in the list can return results by the requested date. The check only
        reads: it places the whole order from today, as urgent work, after the urgent work the laboratory holds, and
        counts a subcontracted way's turnaround from today. The latest finish plus the safety margin is the earliest
        feasible date. Returns that date, or False with the reasons it cannot be given."""
        for way in ways:
            if way.sudo().subcontractor_id and not way.sudo().turnaround_days:
                return {
                    "date": False,
                    "feasible": False,
                    "reasons": [self.env._("%s has no turnaround.", way.display_name)],
                }
        earliest = self._earliest_return(ways, fields.Datetime.now(), 0, urgent=True, strict=True)
        if not earliest["date"]:
            return {"date": False, "feasible": False, "reasons": earliest["reasons"]}
        return {
            "date": earliest["date"],
            "feasible": bool(requested_date) and earliest["date"] <= requested_date,
            "reasons": [],
        }

    def _commit_on_receipt(self):
        """Fix the expected return date of requests that have none when their first sample is received: the receipt
        day plus the request's turnaround in working days, or later when the laboratory's held work leaves its tests to
        finish later."""
        now = fields.Datetime.now()
        for request in self.sudo().filtered(
            lambda request: bool(not request.committed_date and request.turnaround_days)
        ):
            ways = [
                test.accepted_method_id or test.parameter_method_id
                for test in request.sample_ids.test_ids
                if test.status != "cancelled" and (test.accepted_method_id or test.parameter_method_id)
            ]
            earliest = self._earliest_return(ways, now, request.turnaround_days, exclude=request)
            request.with_context(**{CHANGING_COMMITTED_DATE: True}).committed_date = earliest[
                "date"
            ] or self._date_after_working_days(self.env[MODEL_SAMPLE_TEST]._local_day(now), request.turnaround_days)

    def _finish_collections(self):
        """Mark done the open sample collection tasks of requests none of whose samples are still expected."""
        tasks = self.env[MODEL_TASK].sudo()
        task_type = self.env[MODEL_TASK_TYPE].sudo().search([("code", "=", SAMPLE_COLLECTION_CODE)], limit=1)
        for request in self.sudo().filtered(lambda request: "expected" not in request.sample_ids.mapped("status")):
            tasks.search(
                [
                    ("document_model", "=", request._name),
                    ("document_id", "=", request.id),
                    ("type_id", "=", task_type.id),
                    ("status", "in", ("open", "assigned", "in_progress")),
                ]
            ).write({"status": "done", "done_at": fields.Datetime.now()})
