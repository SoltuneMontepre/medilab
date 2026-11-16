from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain
from odoo.tools import format_list

from odoo.addons.sol_laboratory.constants.catalog import ACCEPTED, REGULATIONS_ACCEPTED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_CODE_MIXIN,
    MODEL_DEPARTMENT,
    MODEL_EXPECTED_SAMPLING,
    MODEL_LOCATION,
    MODEL_LOCK_MIXIN,
    MODEL_PARAMETER_METHOD_SAMPLE_TYPE,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_REGULATION,
    MODEL_SAMPLE,
    MODEL_SAMPLE_HANDOVER,
    MODEL_SAMPLE_TEST,
    MODEL_SAMPLE_TYPE,
    MODEL_TASK,
    MODEL_TASK_TYPE,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.constants.notifications import EVENT_SAMPLE_INSUFFICIENT
from odoo.addons.sol_laboratory.constants.tasks import (
    SAMPLE_COLLECTION_CODE,
    SAMPLE_TEST_CODE,
)
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REQUEST_READER_GROUP
from odoo.addons.sol_laboratory.services.record_id import persisted_id

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample as SampleBase
else:
    SampleBase = object

CANCELLABLE_STATUSES = ("expected", "received", "on_hold", "testing")
FINISHED_STATUSES = ("rejected", "reported", "retained", "disposed", "returned", "cancelled")
RECEIPT_STATUS = {"good": "received", "unusable": "rejected", "insufficient": "on_hold"}
CONDITIONS = [("good", "Good"), ("unusable", "Unusable"), ("insufficient", "Insufficient")]


def _progress(statuses, sent, done):
    """The status of a sample or request whose parts have the statuses, given the part status that waits for approval
    and the one that is approved; None leaves it as it is."""
    if statuses and all(status == done for status in statuses):
        return "completed"
    if statuses and all(status in (sent, done) for status in statuses):
        return "awaiting_approval"
    if any(status in ("testing", "outsourced", sent, done) for status in statuses):
        return "testing"
    return None


# Mẫu
class Sample(models.Model, SampleBase):
    _name = MODEL_SAMPLE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_CODE_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Sample"
    _order = "id desc"
    _rec_name = "code"
    # A sample is cancelled, never archived or deleted.
    _permission_actions = ("read", "create", "edit")
    # The Medilab Mobile screen that opens it.
    _mobile_screen = "sample"
    _audit_children = ("test_ids", "handover_ids", "expected_sampling_ids", "return_ids")

    if not TYPE_CHECKING:
        # Unique laboratory code (mã PTN) from a sequence, such as PTN.2026.0001; the only name testers see.
        code = fields.Char(string="Lab Code", required=True, copy=False, readonly=True)
        # The test request the sample belongs to.
        request_id = fields.Many2one(
            MODEL_TEST_REQUEST, string="Test Request", required=True, ondelete="cascade", index=True
        )
        # Name the customer gives the sample, such as "Lavie bottled water 1 L"; hidden from testers.
        customer_sample_name = fields.Char(
            string="Customer's Sample Name", required=True, index="trigram", groups=TEST_REQUEST_READER_GROUP
        )
        # The sample type (nền mẫu), such as bottled drinking water.
        sample_type_id = fields.Many2one(MODEL_SAMPLE_TYPE, required=True, ondelete="restrict", index=True)
        # Whether the sample is solid, liquid, gas or semi-solid.
        physical_state = fields.Selection(
            [("solid", "Solid"), ("liquid", "Liquid"), ("gas", "Gas"), ("semi_solid", "Semi-solid")], required=True
        )
        # Form the sample comes in, such as "whole bottle".
        sample_form = fields.Char(string="Form")
        # Container the sample comes in, such as "1 L bottle".
        container_type = fields.Char(string="Container")
        # The regulation the sample's results are compared with; empty when none.
        regulation_id = fields.Many2one(MODEL_REGULATION, ondelete="restrict", index="btree_not_null")
        # Why the sample keeps a regulation that is no longer in force; empty while it is.
        regulation_notice = fields.Char(compute="_compute_regulation_notice")
        # Free notes about the sample.
        note = fields.Text()
        # Where the sample is in its lifecycle.
        status = fields.Selection(
            [
                ("expected", "Expected"),
                ("received", "Received"),
                ("on_hold", "On Hold"),
                ("rejected", "Rejected"),
                ("testing", "Testing"),
                ("awaiting_approval", "Awaiting Approval"),
                ("completed", "Completed"),
                ("reported", "Reported"),
                ("retained", "Retained"),
                ("disposed", "Disposed"),
                ("returned", "Returned"),
                ("cancelled", "Cancelled"),
            ],
            required=True,
            default="expected",
            readonly=True,
            copy=False,
            index=True,
        )
        # When the laboratory received the sample in good condition; empty for an unusable or insufficient arrival.
        received_at = fields.Datetime(readonly=True, copy=False)
        # Person who received the sample in good condition.
        received_by_id = fields.Many2one(
            MODEL_PERSON, string="Received By", readonly=True, copy=False, ondelete="restrict"
        )
        # Amount that arrived, such as "2 bottles of 1 L".
        received_quantity = fields.Char(string="Amount Received")
        # Condition staff decide on arrival, before any receipt: good, unusable or insufficient.
        condition = fields.Selection(CONDITIONS)
        # What was wrong with the sample on arrival.
        condition_note = fields.Text(string="Condition Note")
        # Where the sample is stored, such as "Fridge 2, shelf B".
        storage_location = fields.Char(string="Storage Location")
        # The location the sample was taken from, such as a sampling point.
        sampling_location_id = fields.Many2one(
            MODEL_LOCATION, string="Sampling Location", ondelete="restrict", index="btree_not_null"
        )
        # When the head of department last asked for the sample to be collected again.
        recollection_requested_at = fields.Datetime(readonly=True, copy=False)
        # Head of department who asked for the sample to be collected again.
        recollection_requested_by_id = fields.Many2one(
            MODEL_PERSON,
            string="Recollection Requested By",
            readonly=True,
            copy=False,
            ondelete="restrict",
        )
        # True when the sample can be asked for again: insufficient on arrival, or its subcontract delivery failed.
        can_collect_again = fields.Boolean(compute="_compute_can_collect_again")
        # Last day the sample is kept: the report date plus the sample type's retention days.
        retained_until = fields.Date(readonly=True, copy=False)
        # When the sample was disposed of.
        disposed_at = fields.Datetime(readonly=True, copy=False)
        # Person who disposed of the sample.
        disposed_by_id = fields.Many2one(
            MODEL_PERSON, string="Disposed By", readonly=True, copy=False, ondelete="restrict"
        )
        # How the sample was disposed of.
        disposal_note = fields.Text(string="Disposal Method")
        # Parameters tested on the sample.
        test_ids = fields.One2many(MODEL_SAMPLE_TEST, "sample_id", string="Tests")
        # Handovers of the sample to the departments that test it.
        handover_ids = fields.One2many(MODEL_SAMPLE_HANDOVER, "sample_id", string="Handovers")
        # Containers, preservation and amounts expected for the sample, kept from the accepted quotation.
        expected_sampling_ids = fields.One2many(MODEL_EXPECTED_SAMPLING, "sample_id", string="Expected Sampling")
        # Number of physical samples expected: the objects times the sampling groups.
        expected_sample_count = fields.Integer(string="Expected Samples", compute="_compute_expected_sample_count")
        # Photos of the sample taken when it was collected or received; hidden from testers.
        photo_ids = fields.Many2many(
            "ir.attachment",
            "medilab_sample_photo_rel",
            "sample_id",
            "attachment_id",
            string="Photos",
            groups=TEST_REQUEST_READER_GROUP,
        )

    _code_unique = models.Constraint("UNIQUE(code)", "The lab code of a sample must be unique.")

    @api.depends("regulation_id.valid_until")
    def _compute_regulation_notice(self):
        for sample in self:
            sample.regulation_notice = sample.regulation_id._expiry_notice() if sample.regulation_id else False

    @api.depends("expected_sampling_ids.objects", "expected_sampling_ids.group_number")
    def _compute_expected_sample_count(self):
        for sample in self:
            sample.expected_sample_count = sample.expected_sampling_ids._expected_count()

    @api.depends("status", "recollection_requested_at", "test_ids.status", "test_ids.dispatch_ids.status")
    def _compute_can_collect_again(self):
        for sample in self:
            sample.can_collect_again = sample._collectable_again()

    @api.model_create_multi
    def create(self, vals_list):
        samples = super().create(vals_list)
        if self.env.context.get(REGULATIONS_ACCEPTED) is not ACCEPTED:
            samples.filtered("regulation_id")._check_regulation()
        if any("photo_ids" in vals for vals in vals_list):
            samples._link_photos()
        return samples

    def write(self, vals):
        if vals.get("status") and vals["status"] != "disposed" and any(sample.status == "disposed" for sample in self):
            raise UserError(
                self.env._(
                    "A disposed sample cannot be changed back: %s",
                    format_list(self.env, self.filtered(lambda sample: sample.status == "disposed").mapped("code")),
                )
            )
        if vals.get("status") and vals["status"] != "returned" and any(sample.status == "returned" for sample in self):
            raise UserError(
                self.env._(
                    "A returned sample cannot be changed back: %s",
                    format_list(self.env, self.filtered(lambda sample: sample.status == "returned").mapped("code")),
                )
            )
        result = super().write(vals)
        if {"regulation_id", "sample_type_id"} & set(vals):
            self.filtered("regulation_id")._check_regulation()
        if "photo_ids" in vals:
            self._link_photos()
        if "sample_type_id" in vals:
            self.test_ids._refresh_accreditation()
        return result

    def _check_regulation(self):
        # A regulation chosen for a sample, or a sample type chosen for a sample with one, is a new selection.
        for sample in self:
            sample.regulation_id._check_selectable(sample.sample_type_id)

    def _cancel(self):
        cancelled = self.filtered(lambda sample: sample.status in CANCELLABLE_STATUSES)
        cancelled.status = "cancelled"
        self.test_ids._cancel()
        # A held sample is no longer collected again.
        cancelled._open_collection_tasks().write({"status": "cancelled"})

    def _open_collection_tasks(self):
        tasks = self.env[MODEL_TASK].sudo()
        return tasks.search(
            Domain("type_id.code", "=", SAMPLE_COLLECTION_CODE)
            & Domain("document_model", "=", MODEL_SAMPLE)
            & Domain("document_id", "in", self.ids)
            & tasks._in_use_domain()
        )

    def _follow_tests(self):
        """Move the samples, then their test requests, along with their tests. Cancelled tests and samples, and
        rejected samples, do not count."""
        # A completed sample goes back to testing when the lab head sends one of its results back.
        for sample in self.filtered(
            lambda sample: sample.status in ("received", "testing", "awaiting_approval", "completed")
        ):
            tests = sample.test_ids.filtered(lambda test: test.status != "cancelled")
            status = _progress(tests.mapped("status"), "result_entered", "approved")
            if status and status != sample.status:
                sample.status = status
        for request in self.request_id:
            samples = request.sample_ids.filtered(lambda sample: sample.status not in ("cancelled", "rejected"))
            status = _progress(samples.mapped("status"), "awaiting_approval", "completed")
            if status in request._next_statuses():
                request._set_status(status)

    def _in_use_domain(self):
        return Domain("status", "not in", FINISHED_STATUSES)

    def action_receive(self, quantity, condition, condition_note=None, storage_location=None):
        """Record the condition staff decide on arrival. Only a sample in good condition is received; the system
        rejects an unusable one and puts an insufficient one on hold, neither of them received."""
        self.request_id.sudo()._check_sample_intake()
        if condition not in RECEIPT_STATUS:
            raise UserError(self.env._("Condition must be good, unusable or insufficient."))
        if not quantity:
            raise UserError(self.env._("Enter the amount received."))
        if condition == "unusable" and not condition_note:
            raise UserError(self.env._("Enter why the sample cannot be tested."))
        if any(sample.status != "expected" for sample in self):
            raise UserError(self.env._("Only an expected sample can be received."))
        self.write(
            {
                "received_quantity": quantity,
                "condition": condition,
                "condition_note": condition_note,
                "storage_location": storage_location,
                "status": RECEIPT_STATUS[condition],
            }
        )
        if condition == "good":
            self._record_receipt()
        elif condition == "insufficient":
            self._tell_department_heads()

    def _record_receipt(self):
        """Record who received the samples and when, the first time they arrive in good condition; their requests and
        testing work follow."""
        unreceived = self.filtered(lambda sample: not sample.received_at)
        if unreceived:
            unreceived.write({"received_at": fields.Datetime.now(), "received_by_id": self._current_person().id})
        # Receiving the sample is the permission that matters; its request follows with full rights.
        for request in self.request_id.sudo():
            if "sample_received" in request._next_statuses():
                request._set_status("sample_received")
        self._open_testing_work()

    def action_receive_entered(self):
        for sample in self:
            if not sample.received_quantity or not sample.condition:
                raise UserError(self.env._("Enter the amount received and the condition of %s.", sample.code))
            sample.action_receive(
                sample.received_quantity, sample.condition, sample.condition_note, sample.storage_location
            )

    def action_receive_more(self, quantity, storage_location=None):
        if any(sample.status != "on_hold" for sample in self):
            raise UserError(self.env._("Only a sample on hold can receive more sample."))
        if not quantity:
            raise UserError(self.env._("Enter the amount received."))
        vals = {"status": "received", "received_quantity": quantity}
        if storage_location is not None:
            vals["storage_location"] = storage_location
        self.write(vals)
        self._record_receipt()
        # The sample is back, so its collection is done.
        self._open_collection_tasks().write({"status": "done", "done_at": fields.Datetime.now()})
        # A sample collected again after a failed subcontract delivery goes back to testing when its tests had started.
        self._follow_tests()

    def action_receive_more_entered(self):
        for sample in self:
            if not sample.received_quantity:
                raise UserError(self.env._("Enter the amount received for %s.", sample.code))
            sample.action_receive_more(sample.received_quantity, sample.storage_location)

    def action_request_recollection(self):
        """The head of a department testing the samples asks for them to be collected again: an insufficient sample on
        hold, or a received one whose delivery to a subcontractor failed, which keeps its lab code, sample tests and
        testing tasks and waits on hold. Each gets a collection task in the queue of sample delivery staff, at the
        customer's address; they claim it and plan its time."""
        person = self._current_person()
        task_type = self.env[MODEL_TASK_TYPE].sudo().search([("code", "=", SAMPLE_COLLECTION_CODE)], limit=1)
        if task_type.route != "role":
            raise UserError(
                self.env._("Route the %s task type to the role of sample delivery staff first.", task_type.name)
            )
        for sample in self:
            if sample.status == "on_hold" and sample.recollection_requested_at:
                raise UserError(self.env._("Collecting %s again is already asked for.", sample.code))
            if not sample._collectable_again():
                raise UserError(
                    self.env._(
                        "Only a sample on hold, or one whose delivery to a subcontractor failed, is collected again: %s",
                        sample.code,
                    )
                )
            # The head of a department is its manager.
            if not self.env.su and self.env.user not in sample.sudo()._test_departments().manager_id.user_id:
                raise UserError(
                    self.env._(
                        "Only the head of a department that tests %s asks for it to be collected again.", sample.code
                    )
                )
        self.write(
            {
                "status": "on_hold",
                "recollection_requested_at": fields.Datetime.now(),
                "recollection_requested_by_id": person.id,
            }
        )
        for sample in self.sudo():
            self.env[MODEL_TASK].sudo().create(
                {
                    "type_id": task_type.id,
                    "name": self.env._("Collect %s again", sample.code),
                    "document_model": MODEL_SAMPLE,
                    "document_id": sample.id,
                    "note": sample.request_id.customer_id.partner_id._display_address(),
                }
            )

    def _collectable_again(self):
        """True when the sample is on hold after arriving insufficient, or received with a failed subcontract delivery
        that nobody has asked to collect it again after."""
        self.ensure_one()
        if self.status == "on_hold":
            return not self.recollection_requested_at
        return self.status in ("received", "testing") and bool(self._failed_deliveries())

    def _failed_deliveries(self):
        """The dispatches of the sample's outsourced tests that were sent and then cancelled, as a failed delivery is,
        after the sample was last asked for again, while no other dispatch takes those tests."""
        self.ensure_one()
        tests = self.sudo().test_ids.filtered(
            lambda test: (
                test.status == "outsourced"
                and not test.dispatch_ids.filtered(lambda dispatch: dispatch.status != "cancelled")
            )
        )
        requested = self.recollection_requested_at
        # A cancelled dispatch no longer changes, so its last change is its cancellation.
        return tests.dispatch_ids.filtered(
            lambda dispatch: (
                bool(dispatch.sent_date)
                and (not requested or bool(dispatch.write_date and dispatch.write_date > requested))
            )
        )

    def _retain(self, report_day):
        """Keep the reported samples whose sample type is kept until the report day plus its retention days."""
        for sample in self.filtered(lambda sample: sample.sample_type_id.is_retained):
            sample.write(
                {
                    "status": "retained",
                    "retained_until": report_day + timedelta(days=sample.sample_type_id.retention_days or 0),
                }
            )

    def action_dispose(self, method=None):
        if any(sample.status == "disposed" for sample in self):
            raise UserError(self.env._("A disposed sample cannot be disposed of again."))
        for sample in self:
            if not sample._disposal_allowed():
                raise UserError(
                    self.env._(
                        "Only a sample that is not kept, whose retention is over or whose test request was cancelled "
                        "can be disposed of: %s",
                        sample.code,
                    )
                )
            if not (method or sample.disposal_note or sample.sample_type_id.disposal_method):
                raise UserError(
                    self.env._("Sample %s needs a disposal method, on the sample or on its sample type.", sample.code)
                )
        person = self._current_person()
        now = fields.Datetime.now()
        for sample in self:
            sample.write(
                {
                    "disposal_note": method or sample.disposal_note or sample.sample_type_id.disposal_method,
                    "disposed_at": now,
                    "disposed_by_id": person.id,
                    "status": "disposed",
                }
            )
        self.env[MODEL_TASK]._close_for_document(self, "dispose")

    def action_attach_photo(self, photo, name="photo.jpg"):
        """The mobile app attaches a photo taken when the sample is collected or received."""
        self.ensure_one()
        attachment = self.env["ir.attachment"].create(
            {"name": name, "raw": photo, "res_model": self._name, "res_id": self.id}
        )
        self.write({"photo_ids": [Command.link(persisted_id(attachment))]})
        return attachment

    def _disposal_allowed(self):
        self.ensure_one()
        if self.status == "cancelled":
            return True
        if self.status == "reported":
            return not self.sample_type_id.is_retained
        return self._retention_over()

    def _retention_over(self):
        """True when the sample is retained and its last day of retention has come."""
        self.ensure_one()
        return self.status == "retained" and bool(self.retained_until) and self.retained_until <= self._company_today()

    def _open_testing_work(self):
        tasks = self.env[MODEL_TASK].sudo()
        handovers = self.env[MODEL_SAMPLE_HANDOVER].sudo()
        for sample in self:
            departments = self.env[MODEL_DEPARTMENT]
            for test, department in sample._department_by_test().items():
                if not department:
                    continue
                departments |= department
                if tasks.search_count(
                    [
                        ("type_id.code", "=", SAMPLE_TEST_CODE),
                        ("document_model", "=", MODEL_SAMPLE_TEST),
                        ("document_id", "=", test.id),
                    ]
                ):
                    continue
                test._open_testing_task(department)
            for department in departments:
                if handovers.search_count([("sample_id", "=", sample.id), ("department_id", "=", department.id)]):
                    continue
                handovers.create({"sample_id": sample.id, "department_id": department.id})

    def _tell_department_heads(self):
        for sample in self:
            # The head of a department is its manager.
            heads = sample._test_departments().sudo().manager_id.user_id.partner_id
            self.env["mail.message"].raise_event(
                EVENT_SAMPLE_INSUFFICIENT,
                sample,
                f"sample:{sample.id}:insufficient",
                self.env._("Sample %s arrived insufficient and is on hold.", sample.code),
                subject=sample.code,
                partners=heads,
            )

    def _department_by_test(self):
        self.ensure_one()
        defaults = self.env[MODEL_PARAMETER_METHOD_SAMPLE_TYPE].search(
            [
                ("parameter_id", "in", self.test_ids.parameter_id.ids),
                ("sample_type_id", "=", self.sample_type_id.id),
                ("is_default", "=", True),
                ("parameter_method_id.department_id", "!=", False),
            ]
        )
        department_of = {default.parameter_id.id: default.parameter_method_id.department_id for default in defaults}
        empty = self.env[MODEL_DEPARTMENT]
        # A test keeps to the way the customer accepted, and so to its department; the department of the default way
        # outsources a test accepted on a subcontracted way.
        return {
            test: test.accepted_method_id.department_id or department_of.get(test.parameter_id.id, empty)
            for test in self.test_ids
        }

    def _test_departments(self):
        self.ensure_one()
        return self.env[MODEL_DEPARTMENT].union(*self._department_by_test().values())

    def _retention_department(self):
        # The department that keeps the sample: the first it was handed over to.
        self.ensure_one()
        return (self.handover_ids.sorted("id").department_id or self._test_departments())[:1]

    def _link_photos(self):
        for sample in self:
            photos = sample.photo_ids.filtered(
                lambda photo, sample=sample: photo.res_model != sample._name or photo.res_id != sample.id
            )
            if photos:
                photos.write({"res_model": sample._name, "res_id": sample.id})

    def _current_person(self):
        person = self.env[MODEL_PERSON]._current()
        if not person:
            raise UserError(self.env._("Only a person can do this."))
        return person

    @api.model
    def _company_today(self):
        return datetime.now(ZoneInfo(self.env.company.tz or "UTC")).date()

    @api.model
    def _company_datetime(self, day, hour, minute=0):
        local = datetime.combine(day, time(hour, minute), tzinfo=ZoneInfo(self.env.company.tz or "UTC"))
        return local.astimezone(UTC).replace(tzinfo=None)
