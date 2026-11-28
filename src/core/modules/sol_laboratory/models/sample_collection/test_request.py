from datetime import date
from typing import TYPE_CHECKING, Literal

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain
from odoo.tools import format_list

from odoo.addons.sol_laboratory.constants.catalog import ACCEPTED, REGULATIONS_ACCEPTED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_CODE_MIXIN,
    MODEL_COMMITTED_DATE_CHANGE,
    MODEL_CUSTOMER,
    MODEL_EXPECTED_SAMPLING,
    MODEL_LOCK_MIXIN,
    MODEL_PARAMETER_METHOD,
    MODEL_PERMISSION_MIXIN,
    MODEL_SAMPLE,
    MODEL_SAMPLE_TEST,
    MODEL_TEST_REPORT,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.constants.xml_ids import SAMPLE_LABEL_REPORT, TEST_REPORT_READER_GROUP

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_request as TestRequestBase
else:
    TestRequestBase = object

# The statuses each status can move to.
TRANSITIONS = {
    "draft": ("confirmed", "cancelled"),
    "confirmed": ("sample_received", "cancelled"),
    "sample_received": ("testing", "cancelled"),
    "testing": ("awaiting_approval", "completed", "cancelled"),
    "awaiting_approval": ("testing", "completed"),
    "completed": ("reported", "testing"),
    "reported": (),
    "cancelled": (),
}
FINISHED_STATUSES = ("reported", "cancelled")


# Yêu Cầu Thử Nghiệm
class TestRequest(models.Model, TestRequestBase):
    _name = MODEL_TEST_REQUEST
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_CODE_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Test Request"
    _order = "priority desc, request_date desc, id desc"
    _rec_name = "code"
    # A test request is cancelled, never archived or deleted.
    _permission_actions = ("read", "create", "edit")
    _audit_children = ("sample_ids", "committed_date_change_ids")
    _lock_free_buttons = ("action_print_labels", "action_open_collection_tasks")

    if not TYPE_CHECKING:
        # Unique code of the request, such as YC.26.11.0001; filled from a sequence when left empty.
        code = fields.Char(required=True, copy=False)
        # The customer who asks for the tests.
        customer_id = fields.Many2one(MODEL_CUSTOMER, required=True, ondelete="restrict", index=True)
        # Date the request was made.
        request_date = fields.Date(required=True, default=fields.Date.context_today, index=True)
        # Date the customer wants the results.
        requested_date = fields.Date()
        # Expected return date: the date Sales promised the customer the results. Only Sales changes it, with the
        # customer's agreement, through Change Return Date.
        committed_date = fields.Date(string="Expected Return Date")
        # True for an accepted priority request: the laboratory's check said it can meet the requested date, so the
        # request's tests are urgent.
        priority = fields.Boolean(string="Priority Order", compute="_compute_priority", store=True, readonly=True)
        # Badge label showing whether the request is priority or standard.
        priority_badge = fields.Selection(
            [("priority", "Priority"), ("standard", "Standard")],
            string="Priority",
            compute="_compute_priority_badge",
        )
        # Working days results take from sample receipt, the longest standard turnaround of the accepted ways; it fixes
        # the expected return date at receipt when none was agreed before.
        turnaround_days = fields.Integer(
            string="Turnaround (working days)", compute="_compute_turnaround_days", store=True, readonly=False
        )
        # Language the customer wants the report in.
        report_language = fields.Selection(
            [("vi", "Vietnamese"), ("en", "English"), ("bilingual", "Bilingual")], required=True, default="bilingual"
        )
        # How the report reaches the customer.
        delivery_method = fields.Selection(
            [("in_person", "In Person"), ("post", "By Post"), ("email", "By Email"), ("other", "Other")],
            required=True,
            default="in_person",
        )
        # How to deliver when the delivery method is other, or details such as the postal address.
        delivery_note = fields.Text()
        # The contact who receives the report; the customer's own contact when empty.
        report_recipient_id = fields.Many2one("res.partner", ondelete="restrict", index="btree_not_null")
        # Where the request is in its lifecycle.
        status = fields.Selection(
            [
                ("draft", "Draft"),
                ("confirmed", "Confirmed"),
                ("sample_received", "Sample Received"),
                ("testing", "Testing"),
                ("awaiting_approval", "Awaiting Approval"),
                ("completed", "Completed"),
                ("reported", "Reported"),
                ("cancelled", "Cancelled"),
            ],
            required=True,
            default="draft",
            readonly=True,
            copy=False,
            index=True,
        )
        # Free notes about the request.
        note = fields.Text()
        # True for a request created from a confirmed order, whose samples keep what the customer agreed.
        from_order = fields.Boolean(readonly=True, copy=False)
        # Number of the order the request was created from, kept as text when uninstalling E-commerce drops the link.
        order_number = fields.Char(readonly=True, copy=False, index="trigram")
        # Samples of the request.
        sample_ids = fields.One2many(MODEL_SAMPLE, "request_id", string="Samples")
        # Sample tests the laboratory cancelled with a reason; the report leaves them out.
        cancelled_test_ids = fields.Many2many(
            MODEL_SAMPLE_TEST, string="Cancelled Tests", compute="_compute_cancelled_test_ids"
        )
        # Changes of the expected return date, the latest first, each with the customer's confirmation.
        committed_date_change_ids = fields.One2many(
            MODEL_COMMITTED_DATE_CHANGE, "request_id", string="Committed Date Changes", readonly=True
        )
        # Reports of the request, one per version.
        report_ids = fields.One2many(
            MODEL_TEST_REPORT,
            "request_id",
            string="Test Reports",
            groups=TEST_REPORT_READER_GROUP,
        )

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a test request must be unique.")

    @api.depends("sample_ids.test_ids.cancel_reason")
    def _compute_cancelled_test_ids(self):
        for request in self:
            request.cancelled_test_ids = request.sample_ids.test_ids.filtered("cancel_reason")

    @api.depends(
        "from_order",
        "sample_ids.test_ids.accepted_method_id",
        "sample_ids.test_ids.parameter_method_id",
        "sample_ids.test_ids.status",
    )
    def _compute_turnaround_days(self):
        methods = self.env[MODEL_PARAMETER_METHOD]
        for request in self:
            if request.from_order:
                request.turnaround_days = request.turnaround_days
                continue
            ways = methods.concat(
                *[
                    test.accepted_method_id or test.parameter_method_id
                    for test in request.sample_ids.test_ids
                    if test.status != "cancelled" and (test.accepted_method_id or test.parameter_method_id)
                ]
            )
            request.turnaround_days = request._turnaround(ways)["days"] if ways else 0

    @api.depends("from_order", "requested_date", "request_date", "turnaround_days")
    def _compute_priority(self):
        for request in self:
            if request.from_order:
                if "_medilab_order_priority" in self.env.context:
                    request.priority = self.env.context["_medilab_order_priority"]
                else:
                    request.priority = request.priority
                continue
            if not (request.requested_date and request.turnaround_days):
                request.priority = False
                continue
            base_day = request.request_date or fields.Date.context_today(request)
            standard = request._date_after_working_days(base_day, request.turnaround_days)
            request.priority = bool(standard and request.requested_date < standard)

    @api.depends("priority")
    def _compute_priority_badge(self):
        for request in self:
            request.priority_badge = "priority" if request.priority else "standard"

    def action_confirm(self):
        self._set_status("confirmed")

    @api.model
    def create_from_order(
        self,
        customer,
        samples,
        committed_date: date | str | Literal[False] = False,
        report_language="bilingual",
        delivery_method="in_person",
        delivery_note=False,
        report_recipient: models.BaseModel | Literal[False] = False,
        requested_date: date | str | Literal[False] = False,
        priority=False,
        turnaround_days=0,
    ):
        # E-commerce calls this when an order is confirmed, with one entry per sample on the quotation. The samples keep
        # the regulations the customer accepted; an entry's sampling is the sampling snapshot it keeps, copied onto the
        # sample.
        accepted = self.with_context(**{REGULATIONS_ACCEPTED: ACCEPTED, "_medilab_order_priority": bool(priority)})
        request = accepted.create(
            {
                "customer_id": customer.id,
                "from_order": True,
                "requested_date": requested_date,
                "committed_date": committed_date,
                "priority": priority,
                "turnaround_days": turnaround_days,
                "report_language": report_language,
                "delivery_method": delivery_method,
                "delivery_note": delivery_note,
                "report_recipient_id": report_recipient.id if report_recipient else False,
                "sample_ids": [
                    Command.create(
                        {
                            "customer_sample_name": sample["customer_sample_name"],
                            "sample_type_id": sample["sample_type_id"],
                            "physical_state": sample.get("physical_state") or False,
                            "regulation_id": sample.get("regulation_id") or False,
                            "test_ids": [
                                Command.create(test) for test in self._sample_tests_from_lines(sample.get("lines", ()))
                            ],
                        }
                    )
                    for sample in samples
                ],
            }
        )
        for sample, values in zip(request.sample_ids.sorted("id"), samples, strict=True):
            if values.get("sampling"):
                values["sampling"]._copy_to(MODEL_EXPECTED_SAMPLING, {"sample_id": sample.id})
        return request.with_env(self.env)

    @api.model
    def _sample_tests_from_lines(self, lines):
        # A package line carries the parameters of the package; any other line is one parameter. A parameter with an
        # accepted way of testing is tested by it.
        parameters = []
        for line in lines:
            parameters.extend(line.get("parameters", [line]))
        tests = []
        for parameter in parameters:
            test = {"parameter_id": parameter["parameter_id"], "quantity": parameter.get("quantity", 1)}
            if parameter.get("parameter_method_id"):
                test["parameter_method_id"] = test["accepted_method_id"] = parameter["parameter_method_id"]
            tests.append(test)
        return tests

    def _check_ready_to_confirm(self):
        for request in self:
            if not request.sample_ids:
                raise UserError(
                    self.env._(
                        "Test request %(code)s needs at least one sample before it can be confirmed.",
                        code=request.code,
                    )
                )
            empty = request.sample_ids.filtered(lambda sample: not sample.test_ids)
            if empty:
                raise UserError(
                    self.env._(
                        "Add at least one parameter to %(samples)s before confirming test request %(code)s.",
                        samples=format_list(self.env, empty.mapped("code")),
                        code=request.code,
                    )
                )

    def action_cancel(self):
        self._set_status("cancelled")
        # Editing the request is the permission that matters; its samples and sample tests follow with full rights.
        self.sudo().sample_ids._cancel()

    def action_print_labels(self):
        samples = self.sample_ids._samples_for_labels(allow_partial=True)
        return self.env.ref(SAMPLE_LABEL_REPORT).report_action(samples, config=False)

    def _next_statuses(self):
        self.ensure_one()
        return TRANSITIONS[self.status or ""]

    def _set_status(self, status):
        if status == "confirmed":
            self._check_ready_to_confirm()
        labels = dict(self._fields["status"]._description_selection(self.env))
        for request in self:
            if status not in request._next_statuses():
                raise UserError(
                    self.env._(
                        "Test request %(code)s cannot go from %(current)s to %(next)s.",
                        code=request.code,
                        current=labels[request.status or ""],
                        next=labels[status],
                    )
                )
        self.status = status
        if status == "completed":
            self.env[MODEL_TEST_REPORT]._draft_for(self)

    def _in_use_domain(self):
        return Domain("status", "not in", FINISHED_STATUSES)
