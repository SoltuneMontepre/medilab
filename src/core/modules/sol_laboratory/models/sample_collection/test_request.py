from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain
from odoo.tools import format_list

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_CODE_MIXIN,
    MODEL_CUSTOMER,
    MODEL_PERMISSION_MIXIN,
    MODEL_SAMPLE,
    MODEL_SAMPLE_TEST,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.constants.xml_ids import SAMPLE_LABEL_REPORT

# The statuses each status can move to.
TRANSITIONS = {
    "draft": ("confirmed", "cancelled"),
    "confirmed": ("paid", "sample_received", "cancelled"),
    "paid": ("sample_received", "cancelled"),
    "sample_received": ("testing", "cancelled"),
    "testing": ("awaiting_approval", "completed", "cancelled"),
    "awaiting_approval": ("testing", "completed"),
    "completed": ("reported",),
    "reported": (),
    "cancelled": (),
}
FINISHED_STATUSES = ("reported", "cancelled")


# Yêu Cầu Thử Nghiệm
class TestRequest(models.Model):
    _name = MODEL_TEST_REQUEST
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_CODE_MIXIN]
    _description = "Test Request"
    _order = "request_date desc, id desc"
    _rec_name = "code"
    # A test request is cancelled, never archived or deleted.
    _permission_actions = ("read", "create", "edit")

    # Unique code of the request, such as YC.2026.0001; filled from a sequence when left empty.
    code = fields.Char(required=True, copy=False)
    # The customer who asks for the tests.
    customer_id = fields.Many2one(MODEL_CUSTOMER, required=True, ondelete="restrict", index=True)
    # Date the request was made.
    request_date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    # Date sales promised the customer the results.
    expected_date = fields.Date()
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
            ("paid", "Paid"),
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
    # Samples of the request.
    sample_ids = fields.One2many(MODEL_SAMPLE, "request_id", string="Samples")
    # Sample tests the laboratory cancelled with a reason; the report leaves them out.
    cancelled_test_ids = fields.Many2many(
        MODEL_SAMPLE_TEST, string="Cancelled Tests", compute="_compute_cancelled_test_ids"
    )

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a test request must be unique.")

    @api.depends("sample_ids.test_ids.cancel_reason")
    def _compute_cancelled_test_ids(self):
        for request in self:
            request.cancelled_test_ids = request.sample_ids.test_ids.filtered("cancel_reason")

    def action_confirm(self):
        self._set_status("confirmed")

    @api.model
    def create_from_order(
        self,
        customer,
        samples,
        expected_date=False,
        report_language="bilingual",
        delivery_method="in_person",
        delivery_note=False,
        report_recipient=False,
    ):
        # E-commerce calls this when an order is confirmed, with one entry per sample on the quotation.
        return self.create(
            {
                "customer_id": customer.id,
                "expected_date": expected_date,
                "report_language": report_language,
                "delivery_method": delivery_method,
                "delivery_note": delivery_note,
                "report_recipient_id": report_recipient.id if report_recipient else False,
                "sample_ids": [
                    Command.create(
                        {
                            "customer_sample_name": sample["customer_sample_name"],
                            "sample_type_id": sample["sample_type_id"],
                            "physical_state": sample["physical_state"],
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

    @api.model
    def _sample_tests_from_lines(self, lines):
        # A package line carries the parameters of the package; any other line is one parameter.
        tests = []
        for line in lines:
            if "parameters" in line:
                tests.extend(
                    {"parameter_id": parameter["parameter_id"], "quantity": parameter.get("quantity", 1)}
                    for parameter in line["parameters"]
                )
            else:
                tests.append({"parameter_id": line["parameter_id"], "quantity": line.get("quantity", 1)})
        return tests

    def _credit_blocks_confirmation(self):
        # E-commerce refuses when the request's order has no payment and the customer may not order on credit.
        # A request without an order is never refused.
        self.ensure_one()
        return False

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
            if request._credit_blocks_confirmation():
                raise UserError(
                    self.env._(
                        "Test request %(code)s cannot be confirmed until its order is paid "
                        "or the customer is allowed credit.",
                        code=request.code,
                    )
                )

    def action_cancel(self):
        self._set_status("cancelled")
        # Editing the request is the permission that matters; its samples and sample tests follow with full rights.
        self.sudo().sample_ids._cancel()

    def action_print_labels(self):
        # Labels do not use the company's document layout, so printing never asks to configure it.
        return self.env.ref(SAMPLE_LABEL_REPORT).report_action(self.sample_ids, config=False)

    def _awaits_payment(self):
        # E-commerce makes the request of an order wait for its payment; a request without an order never does.
        self.ensure_one()
        return False

    def _next_statuses(self):
        self.ensure_one()
        statuses = TRANSITIONS[self.status]
        if self.status == "confirmed":
            # A request awaiting payment must go through the paid step; any other request skips it.
            skipped = "sample_received" if self._awaits_payment() else "paid"
            statuses = tuple(status for status in statuses if status != skipped)
        return statuses

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
                        current=labels[request.status],
                        next=labels[status],
                    )
                )
        self.status = status

    def _in_use_domain(self):
        return Domain("status", "not in", FINISHED_STATUSES)
