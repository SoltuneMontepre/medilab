from decimal import Decimal
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_datetime, formatLang

from odoo.addons.sol_laboratory.constants.approvals import (
    STATE_APPROVED,
    STATE_NONE,
    STATE_REJECTED,
    STATE_REQUESTED,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_APPROVAL_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_MAIL_MESSAGE,
    MODEL_MEASUREMENT_UNIT,
    MODEL_PARAMETER_METHOD,
    MODEL_PARAMETER_METHOD_SAMPLE_TYPE,
    MODEL_PERMISSION_MIXIN,
    MODEL_REGULATION,
    MODEL_SAMPLE_TEST,
    MODEL_SAMPLE_TYPE,
    MODEL_TEST_REPORT,
    MODEL_TEST_RESULT,
)
from odoo.addons.sol_laboratory.constants.notifications import EVENT_TEST_RESULT_REJECTED
from odoo.addons.sol_laboratory.fields.nullable_float import NullableFloat
from odoo.addons.sol_laboratory.models.testing.machine_booking import ACTIVE_STATUSES

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_result as TestResultBase
else:
    TestResultBase = object

# The way of testing, sample type, unit and detection limits copied from the catalog, which a new version copies from
# the version it replaces.
SOURCE_FIELDS = ("parameter_method_id", "sample_type_id", "unit_id", "lod", "loq")
# The regulation and its limit copied for the requested comparison, which a new version copies from the version it
# replaces.
LIMIT_FIELDS = (
    "regulation_id",
    "comparison_requested",
    "limit_unit_id",
    "limit_min_set",
    "limit_min",
    "limit_max_set",
    "limit_max",
    "limit_decimals",
    "limit_text",
)
# Fields only the system sets, so the approval chain, who entered the result and what was copied from the catalog
# cannot be bypassed.
SYSTEM_FIELDS = frozenset(
    {
        "is_reported",
        "entered_by_id",
        "entered_at",
        "status",
        "version",
        "replaces_id",
        "is_replaced",
        "booking_id",
        *SOURCE_FIELDS,
        *LIMIT_FIELDS,
    }
)
# The status of a sample test while its reported result is in each approval state.
TEST_STATUS_BY_STATE = {
    STATE_NONE: "testing",
    STATE_REQUESTED: "result_entered",
    STATE_APPROVED: "approved",
    STATE_REJECTED: "testing",
}
# What the tester enters, and what was copied with it: edits stop once a signature stands.
CONTENT_FIELDS = frozenset(
    {
        "value",
        "value_decimals",
        "value_text",
        "machine_id",
        "started_at",
        "conclusion",
        *SOURCE_FIELDS,
        *LIMIT_FIELDS,
    }
)


# Kết Quả Thử Nghiệm
class TestResult(models.Model, TestResultBase):
    _name = MODEL_TEST_RESULT
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_APPROVAL_MIXIN]
    _description = "Test Result"
    _order = "sample_test_id, entered_at desc, version desc, id desc"
    # A result is signed, never archived or deleted.
    _permission_actions = ("read", "create", "edit", "sign")
    # The Medilab Mobile screen that opens it.
    _mobile_screen = "test_result"

    if not TYPE_CHECKING:
        # The sample test measured.
        sample_test_id = fields.Many2one(
            MODEL_SAMPLE_TEST, required=True, ondelete="restrict", index=True, readonly=True
        )
        # The sample measured, shown by its lab code.
        sample_id = fields.Many2one(related="sample_test_id.sample_id")
        # The parameter measured.
        parameter_id = fields.Many2one(related="sample_test_id.parameter_id")
        # The subcontractor that tested it; empty when the laboratory tested it in-house.
        subcontractor_id = fields.Many2one(related="sample_test_id.subcontractor_id")
        # The way of testing the result is measured by, copied from the sample test when the result is created.
        parameter_method_id = fields.Many2one(
            MODEL_PARAMETER_METHOD,
            string="Way of Testing",
            compute="_compute_source",
            store=True,
            ondelete="restrict",
            index="btree_not_null",
        )
        # The sample's type when the result is created, which the unit, detection limits and regulation limit are
        # copied for.
        sample_type_id = fields.Many2one(MODEL_SAMPLE_TYPE, compute="_compute_source", store=True, ondelete="restrict")
        # Limit of detection, copied from the way of testing on the sample type, in the unit; empty when it states none.
        lod = NullableFloat(string="LOD", compute="_compute_source", store=True, min_display_digits=1)
        # Limit of quantification, copied from the way of testing on the sample type, in the unit; empty when it states
        # none.
        loq = NullableFloat(string="LOQ", compute="_compute_source", store=True, min_display_digits=1)
        # The sample's regulation when the result is created; empty when none.
        regulation_id = fields.Many2one(MODEL_REGULATION, compute="_compute_limit", store=True, ondelete="restrict")
        # True when the regulation limits the parameter on some sample type, so the tester assesses the result against
        # it; a parameter the regulation never limits is outside the requested comparison.
        comparison_requested = fields.Boolean(compute="_compute_limit", store=True)
        # True for the result reported to the customer: the latest one entered for the sample test.
        is_reported = fields.Boolean(string="Reported Result", readonly=True, copy=False)
        # Measured value in the unit, stored exactly; 0 for a text result.
        value = fields.Float(min_display_digits=1)
        # Decimals the value shows, such as 3 for 0.010; copied from the way of testing and correctable by the tester.
        value_decimals = fields.Integer(
            string="Decimals", compute="_compute_value_decimals", store=True, readonly=False
        )
        # The result as text when it is not a number, such as "Not detected", in each language.
        value_text = fields.Char(string="Text Result", translate=True)
        # The result as shown: its text, or its value with its decimals.
        value_display = fields.Char(string="Result", compute="_compute_value_display")
        # Text suggested for a value below the LOD or LOQ, such as "<0.05 mg/L (below LOQ)", for the tester to confirm;
        # empty otherwise.
        value_suggestion = fields.Char(string="Suggested Text", compute="_compute_value_suggestion")
        # The unit of the value, copied from the way of testing on the sample type.
        unit_id = fields.Many2one(
            MODEL_MEASUREMENT_UNIT, string="Unit", compute="_compute_source", store=True, ondelete="restrict"
        )
        # The unit of the copied minimum and maximum.
        limit_unit_id = fields.Many2one(
            MODEL_MEASUREMENT_UNIT, string="Limit Unit", compute="_compute_limit", store=True, ondelete="restrict"
        )
        # True when the copied limit has a minimum, which may be 0.
        limit_min_set = fields.Boolean(compute="_compute_limit", store=True)
        # Lowest allowed value, copied from the sample's regulation for the sample's type when the result is created.
        limit_min = fields.Float(string="Minimum", compute="_compute_limit", store=True, min_display_digits=1)
        # True when the copied limit has a maximum, which may be 0.
        limit_max_set = fields.Boolean(compute="_compute_limit", store=True)
        # Highest allowed value, copied from the sample's regulation for the sample's type when the result is created.
        limit_max = fields.Float(string="Maximum", compute="_compute_limit", store=True, min_display_digits=1)
        # Decimals the copied minimum and maximum show on the report, such as 2 for 0.50.
        limit_decimals = fields.Integer(compute="_compute_limit", store=True)
        # The limit as text, copied from the sample's regulation, in each language.
        limit_text = fields.Char(string="Limit", compute="_compute_limit", store=True, translate=True)
        # True when the comparison is requested but no limit was copied: the regulation sets none for the parameter on
        # the sample's exact type.
        limit_missing = fields.Boolean(compute="_compute_limit_missing")
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
        # The booking the measurement ran in; entering the result frees its machine. Empty for an outsourced test.
        booking_id = fields.Many2one(
            MODEL_MACHINE_BOOKING,
            string="Booking",
            compute="_compute_measurement",
            store=True,
            readonly=True,
            ondelete="restrict",
            index=True,
        )
        # The machine the measurement ran on, taken from the booking and correctable by the tester; empty when outsourced.
        machine_id = fields.Many2one(
            MODEL_MACHINE, compute="_compute_measurement", store=True, readonly=False, ondelete="restrict"
        )
        # When the measurement started, taken from the booking's start and correctable by the tester.
        started_at = fields.Datetime(string="Started At", compute="_compute_measurement", store=True, readonly=False)
        # The tester's assessment against the copied limit: pass, fail or insufficient basis; empty outside the requested
        # comparison.
        conclusion = fields.Selection([("pass", "Pass"), ("fail", "Fail"), ("insufficient", "Insufficient Basis")])
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
        is_replaced = fields.Boolean(string="Replaced", readonly=True, copy=False)

    _replaces_unique = models.Constraint("UNIQUE(replaces_id)", "A result is replaced by one newer version.")
    _one_reported = models.UniqueIndex(
        "(sample_test_id) WHERE is_reported AND NOT is_replaced", "A sample test has one reported result."
    )
    _decimals_range = models.Constraint(
        "CHECK(value_decimals BETWEEN 0 AND 15)", "A result shows between 0 and 15 decimals."
    )

    @api.depends("sample_test_id", "entered_at")
    @api.depends_context("tz", "lang")
    def _compute_display_name(self):
        for result in self:
            test = result.sudo().sample_test_id
            entered = format_datetime(self.env, result.entered_at)
            result.display_name = f"{test.sample_id.code} – {test.parameter_id.name} ({entered})"

    def _document_code(self):
        """A push and Medilab Mobile name a result by its sample's lab code."""
        return self.sample_id.code

    # The copy and the decimals are computed apart: the form sends the editable decimals, and Odoo then leaves
    # every field of the same compute method as it was given.
    @api.depends("sample_test_id")
    def _compute_source(self):
        # Only the sample test is a dependency, so later catalog edits leave the copy as it was.
        for result in self:
            if result.replaces_id:
                # A new version keeps what was copied with the version it replaces.
                result.update({name: result.replaces_id[name] for name in SOURCE_FIELDS})
                continue
            test = result.sample_test_id.sudo()
            sample_type = test.sample_id.sample_type_id
            way = test.parameter_method_id or test.parameter_id._default_way(sample_type)
            applicability = way._applicability(sample_type) if way else self.env[MODEL_PARAMETER_METHOD_SAMPLE_TYPE]
            result.parameter_method_id = way
            result.sample_type_id = sample_type
            result.unit_id = applicability.unit_id
            result.lod = applicability.lod
            result.loq = applicability.loq

    @api.depends("sample_test_id")
    def _compute_value_decimals(self):
        for result in self:
            result.value_decimals = result._applicability().result_decimals

    @api.depends("sample_test_id")
    def _compute_limit(self):
        # Only the sample test is a dependency, so a later change to the regulation leaves the copy as it was.
        for result in self:
            if result.replaces_id:
                # A new version keeps the limit copied with the version it replaces.
                result.update({name: result.replaces_id[name] for name in LIMIT_FIELDS})
                continue
            regulation = result.sample_test_id.sudo().sample_id.regulation_id
            limit = result._regulation_limit()
            result.regulation_id = regulation
            result.comparison_requested = result.sample_test_id.parameter_id in regulation.limit_ids.parameter_id
            result.limit_unit_id = limit.unit_id
            result.limit_min_set = limit.min_set
            result.limit_min = limit.min_value
            result.limit_max_set = limit.max_set
            result.limit_max = limit.max_value
            result.limit_decimals = limit.decimals
            result.limit_text = limit.limit_text

    @api.depends("comparison_requested", "limit_min_set", "limit_max_set", "limit_text")
    def _compute_limit_missing(self):
        for result in self:
            result.limit_missing = result.comparison_requested and not (
                result.limit_min_set or result.limit_max_set or result.limit_text
            )

    @api.depends("sample_test_id")
    def _compute_measurement(self):
        for result in self:
            bookings = result.sample_test_id.sudo().booking_ids.filtered(
                lambda other: other.status in (*ACTIVE_STATUSES, "done")
            )
            booking = bookings.sorted("starts_at")[-1:]
            # A new version keeps the booking of the version it replaces.
            result.booking_id = result.replaces_id.booking_id if result.replaces_id else booking
            result.machine_id = booking.machine_id
            result.started_at = booking.starts_at

    @api.depends("value", "value_decimals", "value_text")
    @api.depends_context("lang")
    def _compute_value_display(self):
        for result in self:
            result.value_display = result.value_text or formatLang(
                self.env, result.value, digits=result.value_decimals, rounding_method="HALF-UP"
            )

    @api.depends("value", "value_text", "lod", "loq", "unit_id")
    @api.depends_context("lang")
    def _compute_value_suggestion(self):
        for result in self:
            result.value_suggestion = not result.value_text and result._below_threshold_text(self.env)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not self.env.su:
                for name in SYSTEM_FIELDS:
                    vals.pop(name, None)
            if vals.get("replaces_id"):
                # A new version is the system's copy of the result it replaces, not a measurement.
                continue
            test = self.env[MODEL_SAMPLE_TEST].browse(vals.get("sample_test_id")).sudo()
            refusal = test._result_refusal()
            if refusal:
                raise UserError(refusal)
            # A retest becomes the reported result; the earlier ones stay on record.
            vals["is_reported"] = True
            reported = test.result_ids.filtered("is_reported")
            reported.is_reported = False
            reported.flush_recordset(["is_reported"])
        results = super().create(vals_list)
        results._copy_limit_translations()
        entered = results.filtered(lambda result: not result.replaces_id)
        tests = entered.sample_test_id.sudo()
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

    @api.constrains("value", "value_text")
    def _check_not_negative(self):
        # A new version is the system's copy of a result already accepted, so it is not checked again.
        for result in self.filtered(lambda result: not result.replaces_id):
            if result.value < 0 and not result.value_text and not result.sudo().parameter_method_id.allows_negative:
                raise ValidationError(
                    self.env._(
                        '%s cannot be negative; enter a measurement below the LOD as a text, such as "< LOD".',
                        result.display_name,
                    )
                )

    @api.constrains("conclusion")
    def _check_conclusion(self):
        # Only a requested comparison is assessed, and a missing limit is never a basis for passing or failing.
        for result in self.filtered("conclusion"):
            if not result.comparison_requested:
                raise ValidationError(
                    self.env._(
                        "%s is outside the requested regulation comparison, so it takes no conclusion.",
                        result.display_name,
                    )
                )
            if result.limit_missing and result.conclusion != "insufficient":
                raise ValidationError(
                    self.env._(
                        "The regulation sets no limit for %s on the sample's type, so it can only be assessed as "
                        "insufficient basis.",
                        result.display_name,
                    )
                )

    def write(self, vals):
        moves = "sample_test_id" in vals and any(result.sample_test_id.id != vals["sample_test_id"] for result in self)
        if not self.env.su and (moves or SYSTEM_FIELDS & set(vals)):
            raise UserError(
                self.env._("The system sets the sample test, entry, status and copied catalog values of a result.")
            )
        return super().write(vals)

    def action_use_value_suggestion(self):
        """The tester confirms the suggested text for a value below the LOD or LOQ, in each language; the measured
        value stays as it was entered."""
        self.ensure_one()
        if not self.value_suggestion:
            raise UserError(self.env._("Only a value below its LOD or LOQ has a suggested text."))
        self.value_text = self.value_suggestion
        langs = [code for code, _name in self.env["res.lang"].get_installed()]
        self.update_field_translations(
            "value_text", {lang: self._below_threshold_text(self.with_context(lang=lang).env) for lang in langs}
        )

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
            if self.comparison_requested and not self.conclusion:
                raise UserError(
                    self.env._(
                        "Assess the result against the regulation as pass, fail or insufficient basis before sending it."
                    )
                )
        return super().action_sign()

    def action_withdraw(self):
        """A sent result taken back by its tester gives them their testing task again."""
        withdrawn = super().action_withdraw()
        if self.status == STATE_NONE and self.is_reported:
            self.sudo().sample_test_id._reopen_testing_task()
        return withdrawn

    def _regulation_limit(self):
        # Only the limit for the sample's exact type applies; a broader type's limit is never used.
        self.ensure_one()
        return self.sample_test_id.sudo().sample_id.regulation_id.limit_ids.filtered(
            lambda limit: (
                limit.parameter_id == self.sample_test_id.parameter_id and limit.sample_type_id == self.sample_type_id
            )
        )

    def _applicability(self):
        # The decimals of the way of testing on the sample type; empty when it does not apply to it.
        self.ensure_one()
        if not self.parameter_method_id:
            return self.env[MODEL_PARAMETER_METHOD_SAMPLE_TYPE]
        return self.parameter_method_id.sudo()._applicability(self.sample_type_id)

    def _below_threshold_text(self, env):
        """The text for a value below the LOD, or else below the LOQ, with the copied threshold and unit in the
        language of env, such as "<0.05 mg/L (below LOQ)"; False when the value is not below either."""
        self.ensure_one()
        for threshold, which in ((self.lod, env._("below LOD")), (self.loq, env._("below LOQ"))):
            if threshold is not False and self.value < threshold:
                digits = max(0, -int(Decimal(repr(threshold)).normalize().as_tuple().exponent))
                shown = formatLang(env, threshold, digits=digits)
                unit = self.unit_id.with_env(env).name
                return f"<{shown} {unit} ({which})" if unit else f"<{shown} ({which})"
        return False

    def _copy_limit_translations(self):
        # The computed copy holds one language; the report needs the limit text in each.
        langs = [code for code, _name in self.env["res.lang"].get_installed()]
        for result in self.sudo():
            source = result.replaces_id or result._regulation_limit()
            if source.limit_text:
                result.update_field_translations(
                    "limit_text", {lang: source.with_context(lang=lang).limit_text for lang in langs}
                )

    def _approval_check_actor(self, rejecting=False):
        level = super()._approval_check_actor(rejecting)
        if (
            not rejecting
            and self.entered_by_id == self.env.user
            and level not in self._approval_sending_level() | self._approval_final_level()
        ):
            raise UserError(self.env._("You entered this result, so another person must sign this level."))
        return level

    def _approval_signs_again(self, level):
        # The head of department who entered and sent a result also approves it at the last level.
        return self.entered_by_id == self.env.user and level == self._approval_final_level()

    def _approval_sending_level(self):
        """The first level of a result signed at more than one level: signing it sends the result, any other approves
        it."""
        levels = self._approval_levels()
        return levels[:1] if len(levels) > 1 else levels.browse()

    def _approval_final_level(self):
        """The last level of the result, the head of department's: its signer may approve a result they entered."""
        return self._approval_levels()[-1:]

    def _approval_department(self):
        # The department that tested it, also once its testing task is done, for the change requests on it.
        return self.sample_test_id._tested_by()

    def _approval_content_fields(self):
        return CONTENT_FIELDS

    def _approval_process_completed(self):
        # The head's approval or rejection is final: a rejected result stays on record and a retest adds a new one.
        # Only the lab head's rejection of the report sends an approved result back.
        return self.status in (STATE_APPROVED, STATE_REJECTED)

    def _change_request_open(self):
        # A rejected result is corrected by a retest, but a rejected correction may belong to a reported sample, which
        # takes no retest, so it is corrected again by a change request.
        return not self.is_replaced and (
            self.status == STATE_APPROVED or (self.status == STATE_REJECTED and bool(self.replaces_id))
        )

    def _new_version(self, change_request):
        """Replace the result by its next version, unsigned and reported in its place; its test goes back to testing in
        the queue of the department that tested it, with the change to make, and its request's unissued report stops
        waiting for signature until the new version is approved."""
        self.ensure_one()
        result = self.sudo()
        result.is_replaced = True
        result.flush_recordset(["is_replaced"])
        version = result.copy(
            {
                "is_reported": result.is_reported,
                "version": result.version + 1,
                "replaces_id": result.id,
            }
        )
        test = version.sample_test_id
        self.env[MODEL_TEST_REPORT]._stop_signing(
            test.sample_id.request_id, self.env._("A reported result is corrected.")
        )
        test._progress(test._work_status())
        test._open_testing_task(test._tested_by(), change_request.requested_change)
        return version

    def _approval_set_state(self, state):
        self.status = state
        if self.is_reported:
            status = TEST_STATUS_BY_STATE[state]
            test = self.sample_test_id
            test._progress(test._work_status() if status == "testing" else status)
            if state == STATE_APPROVED:
                self.env[MODEL_TEST_REPORT]._follow_corrections(test.sample_id.request_id)
            if state == STATE_REJECTED and not self.replaces_id:
                # The rejected result stays on record, and a new testing task with the reason waits in the queue of
                # the department that tested it, unless one is still open. A rejected correction is redone by a change
                # request.
                task = test._latest_testing_task()
                if task.status == "done":
                    test._open_testing_task(task.department_id, self._approval_rejection_reason())

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
