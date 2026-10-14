from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import formatLang

from odoo.addons.sol_laboratory.constants.approvals import (
    STATE_APPROVED,
    STATE_NONE,
    STATE_REJECTED,
    STATE_REQUESTED,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_APPROVAL_MIXIN,
    MODEL_MACHINE,
    MODEL_MAIL_MESSAGE,
    MODEL_MEASUREMENT_UNIT,
    MODEL_PERMISSION_MIXIN,
    MODEL_SAMPLE_TEST,
    MODEL_TEST_RESULT,
)
from odoo.addons.sol_laboratory.constants.notifications import EVENT_TEST_RESULT_REJECTED
from odoo.addons.sol_laboratory.models.sample_collection.subcontract_dispatch import SENT_STATUSES
from odoo.addons.sol_laboratory.models.testing.machine_booking import ACTIVE_STATUSES
from odoo.addons.sol_laboratory.models.testing.sample_test import OPEN_STATUSES

# The statuses of a sample while results can be entered for its tests.
OPEN_SAMPLE_STATUSES = ("received", "testing")
# The statuses of a sample test while a result can be entered for it: open, or sent to a subcontractor.
MEASURABLE_STATUSES = (*OPEN_STATUSES, "outsourced")
# Fields only the system sets, so the approval chain and who entered the result cannot be bypassed.
SYSTEM_FIELDS = frozenset(
    {"attempt", "is_reported", "entered_by_id", "entered_at", "status", "version", "replaces_id", "is_replaced"}
)
# The status of a sample test while its reported result is in each approval state.
TEST_STATUS_BY_STATE = {
    STATE_NONE: "testing",
    STATE_REQUESTED: "result_entered",
    STATE_APPROVED: "approved",
    STATE_REJECTED: "testing",
}
# What the tester enters, and the unit and limit copied with it: edits stop once a signature stands.
CONTENT_FIELDS = frozenset(
    {
        "value",
        "value_decimals",
        "value_text",
        "machine_id",
        "started_at",
        "conclusion",
        "unit_id",
        "limit_unit_id",
        "limit_min_set",
        "limit_min",
        "limit_max_set",
        "limit_max",
        "limit_decimals",
        "limit_text",
    }
)


# Kết Quả Thử Nghiệm
class TestResult(models.Model):
    _name = MODEL_TEST_RESULT
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_APPROVAL_MIXIN]
    _description = "Test Result"
    _order = "sample_test_id, attempt desc, version desc"
    # A result is signed, never archived or deleted.
    _permission_actions = ("read", "create", "edit", "sign")

    # The sample test measured.
    sample_test_id = fields.Many2one(MODEL_SAMPLE_TEST, required=True, ondelete="restrict", index=True, readonly=True)
    # The sample measured, shown by its lab code.
    sample_id = fields.Many2one(related="sample_test_id.sample_id")
    # The parameter measured.
    parameter_id = fields.Many2one(related="sample_test_id.parameter_id")
    # The subcontractor that tested it; empty when the laboratory tested it in-house.
    subcontractor_id = fields.Many2one(related="sample_test_id.subcontractor_id")
    # The regulation the sample's results are compared with; empty when none.
    regulation_id = fields.Many2one(related="sample_test_id.sample_id.regulation_id")
    # Attempt number, 1 for the first measurement and higher for retests.
    attempt = fields.Integer(required=True, default=1, readonly=True, copy=False)
    # True for the result reported to the customer: the latest one entered for the sample test.
    is_reported = fields.Boolean(string="Reported Result", readonly=True, copy=False)
    # Measured value in the unit, stored exactly; 0 for a text result.
    value = fields.Float(min_display_digits=1)
    # Decimals the value shows, such as 3 for 0.010; copied from the way of testing and correctable by the tester.
    value_decimals = fields.Integer(string="Decimals", compute="_compute_value_decimals", store=True, readonly=False)
    # The result as text when it is not a number, such as "Not detected", in each language.
    value_text = fields.Char(string="Text Result", translate=True)
    # The result as shown: its text, or its value with its decimals.
    value_display = fields.Char(string="Result", compute="_compute_value_display")
    # The unit of the value, taken from the way of testing.
    unit_id = fields.Many2one(
        MODEL_MEASUREMENT_UNIT, string="Unit", compute="_compute_unit", store=True, ondelete="restrict"
    )
    # The unit of the copied minimum and maximum.
    limit_unit_id = fields.Many2one(
        MODEL_MEASUREMENT_UNIT, string="Limit Unit", compute="_compute_limit", store=True, ondelete="restrict"
    )
    # True when the copied limit has a minimum, which may be 0.
    limit_min_set = fields.Boolean(compute="_compute_limit", store=True)
    # Lowest allowed value, copied from the sample's regulation when the result is created.
    limit_min = fields.Float(string="Minimum", compute="_compute_limit", store=True, min_display_digits=1)
    # True when the copied limit has a maximum, which may be 0.
    limit_max_set = fields.Boolean(compute="_compute_limit", store=True)
    # Highest allowed value, copied from the sample's regulation when the result is created.
    limit_max = fields.Float(string="Maximum", compute="_compute_limit", store=True, min_display_digits=1)
    # Decimals the copied minimum and maximum show on the report, such as 2 for 0.50.
    limit_decimals = fields.Integer(compute="_compute_limit", store=True)
    # The limit as text, copied from the sample's regulation, in each language.
    limit_text = fields.Char(string="Limit", compute="_compute_limit", store=True, translate=True)
    # The Odoo user who entered the result: a lab QA, or a subcontractor's person for an outsourced test.
    entered_by_id = fields.Many2one(
        "res.users",
        string="Entered By",
        required=True,
        readonly=True,
        ondelete="restrict",
        default=lambda self: self.env.user,
    )
    # When the result was entered, which is when the measurement counts as done.
    entered_at = fields.Datetime(string="Entered At", required=True, readonly=True, default=fields.Datetime.now)
    # The machine the measurement ran on, taken from the booking and correctable by the tester; empty when outsourced.
    machine_id = fields.Many2one(
        MODEL_MACHINE, compute="_compute_measurement", store=True, readonly=False, ondelete="restrict"
    )
    # When the measurement started, taken from the booking's start and correctable by the tester.
    started_at = fields.Datetime(string="Started At", compute="_compute_measurement", store=True, readonly=False)
    # Whether the sample passes its regulation for the parameter; set by the tester, empty without a regulation.
    conclusion = fields.Selection([("pass", "Pass"), ("fail", "Fail")])
    # Where the result is in its approval.
    status = fields.Selection(
        [
            (STATE_NONE, "Draft"),
            (STATE_REQUESTED, "Awaiting Approval"),
            (STATE_APPROVED, "Approved"),
            (STATE_REJECTED, "Rejected"),
        ],
        required=True,
        default=STATE_NONE,
        readonly=True,
        copy=False,
        index=True,
    )
    # Version of the result, 1 for the first and one higher for each version a change request creates.
    version = fields.Integer(required=True, default=1, readonly=True, copy=False)
    # The version this result replaces; empty for version 1.
    replaces_id = fields.Many2one(MODEL_TEST_RESULT, readonly=True, copy=False, ondelete="restrict")
    # True when a newer version replaces this result.
    is_replaced = fields.Boolean(readonly=True, copy=False)

    _attempt_unique = models.Constraint(
        "UNIQUE(sample_test_id, attempt, version)", "A sample test has one result per attempt and version."
    )
    _replaces_unique = models.Constraint("UNIQUE(replaces_id)", "A result is replaced by one newer version.")
    _one_reported = models.UniqueIndex(
        "(sample_test_id) WHERE is_reported AND NOT is_replaced", "A sample test has one reported result."
    )
    _decimals_range = models.Constraint(
        "CHECK(value_decimals BETWEEN 0 AND 15)", "A result shows between 0 and 15 decimals."
    )

    @api.depends("sample_test_id", "attempt")
    def _compute_display_name(self):
        for result in self:
            test = result.sudo().sample_test_id
            result.display_name = f"{test.sample_id.code} – {test.parameter_id.name} #{result.attempt}"

    # The unit and the decimals are computed apart: the form sends the editable decimals, and Odoo then leaves
    # every field of the same compute method as it was given.
    @api.depends("sample_test_id")
    def _compute_unit(self):
        for result in self:
            result.unit_id = result._way_of_testing().unit_id

    @api.depends("sample_test_id")
    def _compute_value_decimals(self):
        for result in self:
            result.value_decimals = result._way_of_testing().result_decimals

    @api.depends("sample_test_id")
    def _compute_limit(self):
        # Only the sample test is a dependency, so a later change to the regulation leaves the copy as it was.
        for result in self:
            limit = result._regulation_limit()
            result.limit_unit_id = limit.unit_id
            result.limit_min_set = limit.min_set
            result.limit_min = limit.min_value
            result.limit_max_set = limit.max_set
            result.limit_max = limit.max_value
            result.limit_decimals = limit.decimals
            result.limit_text = limit.limit_text

    @api.depends("sample_test_id")
    def _compute_measurement(self):
        for result in self:
            bookings = result.sample_test_id.sudo().booking_ids.filtered(
                lambda other: other.status in (*ACTIVE_STATUSES, "done")
            )
            booking = bookings.sorted("starts_at")[-1:]
            result.machine_id = booking.machine_id
            result.started_at = booking.starts_at

    @api.depends("value", "value_decimals", "value_text")
    @api.depends_context("lang")
    def _compute_value_display(self):
        for result in self:
            result.value_display = result.value_text or formatLang(
                self.env, result.value, digits=result.value_decimals, rounding_method="HALF-UP"
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not self.env.su:
                for name in SYSTEM_FIELDS:
                    vals.pop(name, None)
            test = self.env[MODEL_SAMPLE_TEST].browse(vals.get("sample_test_id")).sudo()
            if test.status not in MEASURABLE_STATUSES or test.sample_id.status not in OPEN_SAMPLE_STATUSES:
                raise UserError(
                    self.env._(
                        "A result is entered only for a received sample while %s is waiting, assigned, in testing "
                        "or outsourced.",
                        test.display_name,
                    )
                )
            if test.status == "outsourced" and not test.dispatch_ids.filtered(
                lambda dispatch: dispatch.status in SENT_STATUSES
            ):
                raise UserError(
                    self.env._("Send %s to its subcontractor before entering its result.", test.display_name)
                )
            # A retest becomes the reported result; the earlier ones stay on record.
            vals["attempt"] = max(test.result_ids.mapped("attempt"), default=0) + 1
            vals["is_reported"] = True
            reported = test.result_ids.filtered("is_reported")
            reported.is_reported = False
            reported.flush_recordset(["is_reported"])
        results = super().create(vals_list)
        results._copy_limit_translations()
        tests = results.sample_test_id.sudo()
        tests._start()
        # Entering the result is when the measurement is done; a booking still waiting for a slot is not needed.
        bookings = tests.booking_ids._open()
        bookings.filtered(lambda booking: booking.status == "queued")._set({"status": "cancelled"})
        measured = bookings.filtered(lambda booking: booking.status in ACTIVE_STATUSES)
        if measured:
            measured._set({"status": "done"})
            measured._process_queue()
        return results

    @api.constrains("machine_id")
    def _check_machine(self):
        for result in self:
            if result.machine_id and result.subcontractor_id:
                raise ValidationError(self.env._("An outsourced result has no machine: %s", result.display_name))

    def write(self, vals):
        moves = "sample_test_id" in vals and any(result.sample_test_id.id != vals["sample_test_id"] for result in self)
        if not self.env.su and (moves or SYSTEM_FIELDS & set(vals)):
            raise UserError(self.env._("The system sets the sample test, attempt, entry and status of a result."))
        return super().write(vals)

    def action_sign(self):
        self.ensure_one()
        if self.status == STATE_NONE:
            test = self.sudo().sample_test_id
            if test.status != test._work_status():
                raise UserError(
                    self.env._("Only a result of a sample test in testing or outsourced is sent for approval.")
                )
            if not self.is_reported:
                raise UserError(self.env._("Only the reported result of a sample test is sent for approval."))
            if self.regulation_id and not self.conclusion:
                raise UserError(self.env._("Set the conclusion against the regulation before sending the result."))
        return super().action_sign()

    def _regulation_limit(self):
        self.ensure_one()
        test = self.sample_test_id
        limits = test.sample_id.regulation_id.limit_ids
        return limits.filtered(lambda limit: limit.parameter_id == test.parameter_id)[:1]

    def _way_of_testing(self):
        # The way of testing chosen for the test, or else the parameter's default one.
        self.ensure_one()
        test = self.sample_test_id
        return test.parameter_method_id or test.parameter_id.method_ids.filtered("is_default")[:1]

    def _copy_limit_translations(self):
        # The computed copy holds one language; the report needs the limit text in each.
        langs = [code for code, _name in self.env["res.lang"].get_installed()]
        for result in self.sudo():
            limit = result._regulation_limit()
            if limit.limit_text:
                result.update_field_translations(
                    "limit_text", {lang: limit.with_context(lang=lang).limit_text for lang in langs}
                )

    def _approval_check_actor(self, rejecting=False):
        level = super()._approval_check_actor(rejecting)
        if not rejecting and level != self._approval_sending_level() and self.entered_by_id == self.env.user:
            raise UserError(self.env._("You entered this result, so another person must approve it."))
        return level

    @api.model
    def _approval_sending_level(self):
        """The first level of a chain with more than one level: signing it sends the result, any other approves it."""
        levels = self._approval_chain().level_ids.sorted("sequence")
        return levels[:1] if len(levels) > 1 else levels.browse()

    def _approval_department(self):
        return self.sample_test_id._testing_task().department_id

    def _approval_content_fields(self):
        return CONTENT_FIELDS

    def _approval_process_completed(self):
        # The head's approval or rejection is final: a rejected result stays on record and a retest adds a new one.
        # Only the lab head's rejection of the report sends an approved result back.
        return self.status in (STATE_APPROVED, STATE_REJECTED)

    def _approval_set_state(self, state):
        self.status = state
        if self.is_reported:
            status = TEST_STATUS_BY_STATE[state]
            test = self.sample_test_id
            test._progress(test._work_status() if status == "testing" else status)

    def _send_back(self, note):
        """The lab head sends approved results back to the department that tested them: their signatures are withdrawn,
        and a new testing task with the note waits unassigned in the department's queue."""
        for result in self.sudo():
            result._approval_restart()
            test = result.sample_test_id
            test._open_testing_task(test._tested_by(), note)

    def _approval_notify_rejected(self, reason):
        self.ensure_one()
        # A rejection is final, so the result is rejected at most once.
        self.env[MODEL_MAIL_MESSAGE].raise_event(
            EVENT_TEST_RESULT_REJECTED,
            self,
            f"test_result:{self.id}:rejected",
            self.env._("Result %(result)s was rejected: %(reason)s", result=self.display_name, reason=reason),
            subject=self.display_name,
            partners=self.entered_by_id.partner_id,
        )
