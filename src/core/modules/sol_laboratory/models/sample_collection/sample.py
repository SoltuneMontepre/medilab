from odoo import fields, models
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_CODE_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_REGULATION,
    MODEL_SAMPLE,
    MODEL_SAMPLE_TEST,
    MODEL_SAMPLE_TYPE,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REQUEST_READER_GROUP

CANCELLABLE_STATUSES = ("expected", "received", "testing")
FINISHED_STATUSES = ("rejected", "reported", "retained", "disposed", "cancelled")


# Mẫu
class Sample(models.Model):
    _name = MODEL_SAMPLE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_CODE_MIXIN]
    _description = "Sample"
    _order = "id desc"
    _rec_name = "code"
    # A sample is cancelled, never archived or deleted.
    _permission_actions = ("read", "create", "edit")

    # Unique laboratory code (mã PTN) from a sequence, such as PTN.2026.0001; the only name testers see.
    code = fields.Char(string="Lab Code", required=True, copy=False, readonly=True)
    # The test request the sample belongs to.
    request_id = fields.Many2one(
        MODEL_TEST_REQUEST, string="Test Request", required=True, ondelete="cascade", index=True
    )
    # Name the customer gives the sample, such as "Lavie bottled water 1 L"; hidden from testers.
    customer_sample_name = fields.Char(string="Customer's Sample Name", required=True, groups=TEST_REQUEST_READER_GROUP)
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
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="expected",
        readonly=True,
        copy=False,
        index=True,
    )
    # Parameters tested on the sample.
    test_ids = fields.One2many(MODEL_SAMPLE_TEST, "sample_id", string="Tests")

    _code_unique = models.Constraint("UNIQUE(code)", "The lab code of a sample must be unique.")

    def _cancel(self):
        self.filtered(lambda sample: sample.status in CANCELLABLE_STATUSES).status = "cancelled"
        self.test_ids._cancel()

    def _in_use_domain(self):
        return Domain("status", "not in", FINISHED_STATUSES)
