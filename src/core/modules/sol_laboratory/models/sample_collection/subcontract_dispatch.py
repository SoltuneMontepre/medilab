import math
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.approvals import STATE_NONE
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_CODE_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_ROLE,
    MODEL_SAMPLE_TEST,
    MODEL_SUBCONTRACT_DISPATCH,
    MODEL_SUBCONTRACTOR,
    MODEL_TEST_RESULT,
)
from odoo.addons.sol_laboratory.constants.settings import SAMPLE_DELIVERY_ROLE_PARAMETER

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_subcontract_dispatch as SubcontractDispatchBase
else:
    SubcontractDispatchBase = object

# What goes to whom; fixed once the dispatch is sent.
CONTENT_FIELDS = frozenset({"subcontractor_id", "sample_test_ids"})
# The statuses of a dispatch whose samples have left the laboratory.
SENT_STATUSES = ("sent", "received")


# Phiếu Gửi Thầu Phụ
class SubcontractDispatch(models.Model, SubcontractDispatchBase):
    _name = MODEL_SUBCONTRACT_DISPATCH
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_CODE_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Subcontract Dispatch"
    _order = "id desc"
    _rec_name = "code"
    # A dispatch is cancelled, never archived or deleted.
    _permission_actions = ("read", "create", "edit")

    if not TYPE_CHECKING:
        # Unique code of the dispatch, such as PGTP.2026.0001; filled from a sequence when left empty.
        code = fields.Char(required=True, copy=False, readonly=True)
        # The subcontractor the tests are sent to.
        subcontractor_id = fields.Many2one(MODEL_SUBCONTRACTOR, required=True, ondelete="restrict", index=True)
        # Date the samples were sent.
        sent_date = fields.Date(copy=False)
        # Sample delivery staff who take the samples; empty when a delivery service does.
        courier_id = fields.Many2one(MODEL_PERSON, string="Sample Delivery Staff", ondelete="restrict")
        # Delivery service and tracking number, when a delivery service takes the samples.
        delivery_service = fields.Char(string="Delivery Service and Tracking Number")
        # Date the results are expected back.
        expected_date = fields.Date(index=True)
        # Date the results came back.
        received_date = fields.Date(copy=False)
        # Where the dispatch is: draft, sent, received or cancelled.
        status = fields.Selection(
            [("draft", "Draft"), ("sent", "Sent"), ("received", "Received"), ("cancelled", "Cancelled")],
            required=True,
            default="draft",
            readonly=True,
            copy=False,
        )
        # Free notes about the dispatch.
        note = fields.Text()
        # Sample tests in the dispatch.
        sample_test_ids = fields.Many2many(
            MODEL_SAMPLE_TEST,
            "medilab_subcontract_dispatch_test_rel",
            "dispatch_id",
            "sample_test_id",
            string="Sample Tests",
            ondelete="restrict",
        )
        # People who can take the dispatch: those holding the sample delivery staff role named in the settings.
        courier_choice_ids = fields.Many2many(
            MODEL_PERSON,
            string="Sample Delivery Staff to Choose",
            compute="_compute_courier_choice_ids",
            compute_sudo=True,
        )
        # True when the current user is the sample delivery staff taking the dispatch.
        carried_by_me = fields.Boolean(compute="_compute_carried_by_me", search="_search_carried_by_me")

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a dispatch must be unique.")

    def _compute_courier_choice_ids(self):
        couriers = self._sample_delivery_staff()
        for dispatch in self:
            dispatch.courier_choice_ids = couriers

    @api.model
    def _sample_delivery_staff(self):
        # With full rights: only administrators read who holds a role.
        role_id = self.env["ir.config_parameter"].sudo().get_int(SAMPLE_DELIVERY_ROLE_PARAMETER)
        people = self.env[MODEL_ROLE].sudo().browse(role_id).exists().person_ids
        return self.env[MODEL_PERSON].browse(people.ids)

    def _compute_carried_by_me(self):
        person = self.env[MODEL_PERSON]._current()
        for dispatch in self:
            dispatch.carried_by_me = bool(person) and dispatch.courier_id == person

    def _search_carried_by_me(self, operator, value):
        # By the person's id: sample delivery staff need not read people to see what they carry.
        if operator != "in" or True not in value:
            return NotImplemented
        person = self.env[MODEL_PERSON]._current()
        return Domain("courier_id", "=", person.id) if person else Domain.FALSE

    @api.constrains("subcontractor_id")
    def _check_subcontractor(self):
        for dispatch in self:
            if not dispatch.subcontractor_id._can_be_chosen():
                raise ValidationError(
                    self.env._(
                        "%s cannot be chosen: it is archived or its accreditation has expired.",
                        dispatch.subcontractor_id.display_name,
                    )
                )

    @api.constrains("courier_id")
    def _check_courier(self):
        couriers = self._sample_delivery_staff()
        for dispatch in self:
            if dispatch.courier_id and dispatch.courier_id not in couriers:
                raise ValidationError(
                    self.env._(
                        "%s does not hold the sample delivery staff role named in the Laboratory settings.",
                        dispatch.courier_id.sudo().name,
                    )
                )

    @api.constrains("courier_id", "delivery_service")
    def _check_carrier(self):
        for dispatch in self:
            if dispatch.courier_id and dispatch.delivery_service:
                raise ValidationError(
                    self.env._(
                        "%s is carried by sample delivery staff or by a delivery service, not both.", dispatch.code
                    )
                )

    @api.constrains("subcontractor_id", "sample_test_ids")
    def _check_sample_tests(self):
        for dispatch in self.sudo():
            for test in dispatch.sample_test_ids:
                if test.status != "outsourced" or test.subcontractor_id != dispatch.subcontractor_id:
                    raise ValidationError(
                        self.env._(
                            "%(test)s is not outsourced to %(subcontractor)s.",
                            test=test.display_name,
                            subcontractor=dispatch.subcontractor_id.display_name,
                        )
                    )
            if dispatch.search_count(
                [
                    ("id", "!=", dispatch.id),
                    ("status", "!=", "cancelled"),
                    ("sample_test_ids", "in", dispatch.sample_test_ids.ids),
                ],
                limit=1,
            ):
                raise ValidationError(self.env._("A sample test of %s is already in another dispatch.", dispatch.code))

    @api.model_create_multi
    def create(self, vals_list):
        # A dispatch starts as a draft; only its buttons move it on.
        if not self.env.su:
            for vals in vals_list:
                vals.pop("status", None)
        return super().create(vals_list)

    def write(self, vals):
        if "status" in vals and not self.env.su:
            raise UserError(self.env._("Send, receive or cancel a dispatch with its buttons."))
        if CONTENT_FIELDS & set(vals) and any(dispatch.status != "draft" for dispatch in self):
            raise UserError(self.env._("Only a draft dispatch can change its subcontractor or sample tests."))
        return super().write(vals)

    def action_send(self):
        today = fields.Date.context_today(self)
        for dispatch in self:
            if dispatch.status != "draft":
                raise UserError(self.env._("Only a draft dispatch can be sent: %s", dispatch.code))
            if not dispatch.sample_test_ids:
                raise UserError(self.env._("Add the sample tests to %s before sending it.", dispatch.code))
            dispatch._check_subcontractor()
            if not dispatch.courier_id and not dispatch.delivery_service:
                raise UserError(
                    self.env._("Enter the sample delivery staff or the delivery service taking %s.", dispatch.code)
                )
            sent_date = dispatch.sent_date or today
            if not dispatch.expected_date or dispatch.expected_date < sent_date:
                raise UserError(
                    self.env._("Enter when the results of %s are expected back, not before it is sent.", dispatch.code)
                )
            dispatch._set_status("sent", sent_date=sent_date)

    def action_receive(self):
        if any(dispatch.status != "sent" for dispatch in self):
            raise UserError(self.env._("Only a sent dispatch can be received."))
        self._set_status("received", received_date=fields.Date.context_today(self))

    def action_cancel(self):
        if any(dispatch.status not in ("draft", "sent") for dispatch in self):
            raise UserError(self.env._("Only a draft or sent dispatch can be cancelled."))
        if self.sudo().sample_test_ids.result_ids:
            raise UserError(self.env._("A dispatch whose sample tests have results cannot be cancelled."))
        self._set_status("cancelled")

    def _set_status(self, status, **vals):
        self._check_permission("edit")
        self.sudo().write({"status": status, **vals})

    @api.model
    def _portal_domain(self, user):
        """The sent and received dispatches of the subcontractor the portal user works for."""
        subcontractors = user.partner_id.commercial_partner_id.sudo().subcontractor_ids
        return Domain("subcontractor_id", "in", subcontractors.ids) & Domain("status", "in", SENT_STATUSES)

    @api.model
    def _portal_dispatches(self, user, dispatch_id=None):
        # Read with full rights: the portal pages show them without the customer.
        domain = self._portal_domain(user)
        return self.sudo().search(domain & Domain("id", "=", dispatch_id) if dispatch_id else domain)

    def _portal_enter_result(self, sample_test_id, value, value_text):
        """A subcontractor's person enters the result of a test of the dispatch, as a number or as a text; it waits
        for the laboratory to send it for approval."""
        self.ensure_one()
        test = self.sample_test_ids.filtered(lambda other: other.id == sample_test_id)
        if test.status != "outsourced":
            raise UserError(self.env._("A result is entered only for an outsourced test of this dispatch."))
        if test.result_ids.filtered(lambda result: result.is_reported and result.status == STATE_NONE):
            raise UserError(self.env._("The result of %s is already entered.", test.display_name))
        text = (value_text or "").strip()
        number = (value or "").strip().replace(",", ".")
        if not text and not number:
            raise UserError(self.env._("Enter the result as a number or as a text."))
        try:
            measured = 0.0 if text else float(number)
        except ValueError:
            measured = math.nan
        if not math.isfinite(measured):
            raise UserError(self.env._("%s is not a number.", value))
        return (
            self.env[MODEL_TEST_RESULT]
            .sudo()
            .create({"sample_test_id": test.id, "value": measured, "value_text": text or False})
        )
