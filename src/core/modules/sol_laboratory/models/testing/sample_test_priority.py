from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE_BOOKING,
    MODEL_MAIL_MESSAGE,
    MODEL_PERSON,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SAMPLE_HANDOVER,
    MODEL_SAMPLE_TEST,
)
from odoo.addons.sol_laboratory.constants.notifications import EVENT_SAMPLE_TEST_AT_RISK
from odoo.addons.sol_laboratory.models.testing.machine_booking import OPEN_STATUSES as OPEN_BOOKING_STATUSES
from odoo.addons.sol_laboratory.models.testing.sample_test import OPEN_STATUSES

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample_test as SampleTestPriorityBase
else:
    SampleTestPriorityBase = object

PRIORITY_RANKS = {"urgent": 0, "due_soon": 1, "normal": 2}
# Fields that change where the plan places a test.
PLAN_FIELDS = frozenset({"due_date", "due_date_reason", "marked_urgent"})


# Chỉ Tiêu Của Mẫu: its priority class in the department's plan and its risk of missing the internal due date.
class SampleTestPriority(models.Model, SampleTestPriorityBase):
    _inherit = MODEL_SAMPLE_TEST

    if not TYPE_CHECKING:
        # True when its tester or head of department marked the test urgent, so the plan places it in the urgent class
        # whatever its due date.
        marked_urgent = fields.Boolean(readonly=True, copy=False)
        # Why the test was marked urgent.
        urgent_reason = fields.Text(readonly=True, copy=False)
        # Tester or head of department who marked the test urgent.
        marked_urgent_by_id = fields.Many2one(
            MODEL_PERSON, string="Marked Urgent By", readonly=True, copy=False, ondelete="restrict"
        )
        # True when the test's planned finish is after its internal due date or no free slot lets it finish by then;
        # its tester and head of department are told when it turns true.
        at_risk = fields.Boolean(string="At Risk", readonly=True, copy=False, index=True)
        # The plan's priority class: urgent when marked urgent, due soon when the due date is within the urgency
        # threshold, otherwise normal.
        priority = fields.Selection(
            [("urgent", "Urgent"), ("due_soon", "Due Soon"), ("normal", "Normal")], compute="_compute_priority"
        )
        # True when the current user is the test's tester or heads the department testing it, while it is open.
        can_mark_urgent = fields.Boolean(compute="_compute_can_mark_urgent")

    def write(self, vals):
        result = super().write(vals)
        if PLAN_FIELDS & set(vals):
            self.env[MODEL_MACHINE_BOOKING]._plan(self.sudo().booking_ids.department_id)
        return result

    @api.depends("marked_urgent", "due_date")
    def _compute_priority(self):
        hours = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("urgency_hours")
        until = fields.Datetime.now() + timedelta(hours=hours)
        for test in self:
            if test.marked_urgent:
                test.priority = "urgent"
            elif test.due_date and test.due_date <= until:
                test.priority = "due_soon"
            else:
                test.priority = "normal"

    def _plan_key(self, department):
        """Where the test goes in the department's plan: by priority class, then the earlier committed return date,
        then the earlier arrival in the department."""
        self.ensure_one()
        test = self.sudo()
        handover = (
            self.env[MODEL_SAMPLE_HANDOVER]
            .sudo()
            .search(Domain("sample_id", "=", test.sample_id.id) & Domain("department_id", "=", department.id), limit=1)
        )
        return (
            PRIORITY_RANKS[test.priority or "normal"],
            test.sample_id.request_id.expected_date or date.max,
            handover.received_at or datetime.max,
            test.id,
        )

    @api.depends_context("uid")
    @api.depends("status")
    def _compute_can_mark_urgent(self):
        person = self.env[MODEL_PERSON]._current()
        for test in self:
            test.can_mark_urgent = bool(person) and test.status in OPEN_STATUSES and test._marks_urgent(person)

    def _marks_urgent(self, person):
        """True when the person is the assignee of the test's testing task or heads the department testing it."""
        self.ensure_one()
        test = self.sudo()
        return (
            person == test._testing_task().assignee_id or self.env.user in test._testing_department().manager_id.user_id
        )

    def _mark_urgent(self, reason):
        """The tester or head of department marks the test urgent, with a reason."""
        self.ensure_one()
        self._check_can_mark_urgent()
        if not (reason or "").strip():
            raise UserError(self.env._("Give a reason for marking the test urgent."))
        person = self.env[MODEL_PERSON]._current()
        self.sudo().write({"marked_urgent": True, "urgent_reason": reason, "marked_urgent_by_id": person.id})

    def action_unmark_urgent(self):
        self._check_can_mark_urgent()
        self.sudo().write({"marked_urgent": False, "urgent_reason": False, "marked_urgent_by_id": False})

    def _check_can_mark_urgent(self):
        for test in self:
            if not test.can_mark_urgent:
                raise UserError(
                    self.env._(
                        "Only the tester of %s or the head of the department testing it marks it urgent, while it is "
                        "open.",
                        test.display_name,
                    )
                )

    def _is_at_risk(self):
        """True when the test's open booking finishes after its internal due date, or the plan found no slot that lets
        it finish by then."""
        self.ensure_one()
        test = self.sudo()
        if test.status not in OPEN_STATUSES:
            return False
        bookings = test.booking_ids.filtered(lambda booking: booking.status in OPEN_BOOKING_STATUSES)
        return any(not booking.ends_at or (test.due_date and booking.ends_at > test.due_date) for booking in bookings)

    def _refresh_risk(self):
        """Work out again which tests are at risk; tell the tester and head of those that just became so."""
        tests = self.sudo()
        risky = tests.filtered(lambda test: test._is_at_risk())
        (tests - risky).filtered("at_risk").at_risk = False
        risky._flag_at_risk()

    def _flag_at_risk(self):
        """Flag the tests at risk of missing their internal due date, and tell the tester and head of department of
        each test that was not at risk yet."""
        new = self.sudo().filtered(lambda test: not test.at_risk)
        new.at_risk = True
        stamp = fields.Datetime.to_string(fields.Datetime.now())
        for test in new:
            self.env[MODEL_MAIL_MESSAGE].raise_event(
                EVENT_SAMPLE_TEST_AT_RISK,
                test,
                f"sample_test:{test.id}:at_risk:{stamp}",
                self.env._("%s is at risk of missing its internal due date.", test.display_name),
                subject=test.sample_id.code,
                partners=test._risk_partners(),
            )

    def _risk_partners(self):
        """The contacts told of the tests' risk: the tester of each and the head of the department testing it."""
        partners = self.env["res.partner"]
        for test in self.sudo():
            partners |= test._testing_task().assignee_id.user_id.partner_id
            partners |= test._testing_department().manager_id.user_id.partner_id
        return partners
