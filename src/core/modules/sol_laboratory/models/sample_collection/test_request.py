from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_CODE_MIXIN,
    MODEL_CUSTOMER,
    MODEL_PERMISSION_MIXIN,
    MODEL_SAMPLE,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.constants.xml_ids import SAMPLE_LABEL_REPORT

# The statuses each status can move to.
TRANSITIONS = {
    "draft": ("confirmed", "cancelled"),
    "confirmed": ("paid", "sample_received", "cancelled"),
    "paid": ("sample_received", "cancelled"),
    "sample_received": ("testing", "cancelled"),
    "testing": ("awaiting_approval", "cancelled"),
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

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a test request must be unique.")

    def action_confirm(self):
        self._set_status("confirmed")

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
