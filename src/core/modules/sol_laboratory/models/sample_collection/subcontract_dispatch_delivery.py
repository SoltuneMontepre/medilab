from datetime import date, timedelta
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DEPARTMENT,
    MODEL_MAIL_MESSAGE,
    MODEL_SUBCONTRACT_DISPATCH,
)
from odoo.addons.sol_laboratory.constants.notifications import (
    EVENT_DISPATCH_DELIVERY_FAILED,
    EVENT_DISPATCH_RECEIVED,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_subcontract_dispatch as SubcontractDispatchBase
else:
    SubcontractDispatchBase = object


# Phiếu Gửi Thầu Phụ: carrying it to the subcontractor and its receipt there.
class SubcontractDispatchDelivery(models.Model, SubcontractDispatchBase):
    _inherit = MODEL_SUBCONTRACT_DISPATCH

    if not TYPE_CHECKING:
        # True when the current user may take the draft dispatch to the subcontractor: its sample delivery staff.
        can_hand_over = fields.Boolean(compute="_compute_carrier_actions")
        # True when the current user may record that the delivery of the sent dispatch failed: its sample delivery
        # staff, or a person who edits dispatches.
        can_report_failure = fields.Boolean(compute="_compute_carrier_actions")
        # True when the subcontractor's default contact person is archived, which stops the dispatch being sent.
        contact_person_archived = fields.Boolean(compute="_compute_contact_person_archived")

    @api.depends_context("uid")
    @api.depends("status", "courier_id")
    def _compute_carrier_actions(self):
        editor = self._has_permission("edit")
        for dispatch in self:
            dispatch.can_hand_over = dispatch.status == "draft" and dispatch.carried_by_me
            dispatch.can_report_failure = dispatch.status == "sent" and (editor or dispatch.carried_by_me)

    @api.depends("subcontractor_id")
    def _compute_contact_person_archived(self):
        for dispatch in self:
            contact = dispatch.sudo().subcontractor_id.contact_person_id
            dispatch.contact_person_archived = bool(contact) and not contact.active

    def _turnaround_date(self, sent_date: date) -> date | None:
        """The sent date plus the longest turnaround of the dispatch's ways of testing; None when none has one."""
        self.ensure_one()
        days = [day or 0 for day in self.sudo().sample_test_ids.parameter_method_id.mapped("turnaround_days")]
        return sent_date + timedelta(days=max(days)) if any(days) else None

    def _check_contact_person(self):
        for dispatch in self:
            if dispatch.contact_person_archived:
                raise UserError(
                    self.env._(
                        "The default contact person of %(subcontractor)s is archived. Choose another before sending "
                        "%(dispatch)s.",
                        subcontractor=dispatch.subcontractor_id.display_name,
                        dispatch=dispatch.code,
                    )
                )

    def _hand_over(self, delivery_service: str | bool = False, tracking_number: str | bool = False):
        """The dispatch's sample delivery staff take it, or hand it to a delivery service with its tracking number;
        it is sent from then on."""
        self.ensure_one()
        if not self.can_hand_over:
            raise UserError(self.env._("Only the sample delivery staff taking %s can hand it over.", self.code))
        dispatch = self.sudo()
        dispatch.write({"delivery_service": delivery_service or False, "tracking_number": tracking_number or False})
        dispatch.action_send()

    def _report_failed_delivery(self, reason):
        """The delivery of the sent dispatch failed: it is cancelled with the reason and its tests stay outsourced, so
        the heads of their departments ask for the samples again and put them in a new dispatch."""
        self.ensure_one()
        if not (reason or "").strip():
            raise UserError(self.env._("Give the reason the delivery failed."))
        if not self.can_report_failure:
            raise UserError(
                self.env._(
                    "Only the sample delivery staff carrying %s, or a person who edits dispatches, can record that its "
                    "delivery failed.",
                    self.code,
                )
            )
        dispatch = self.sudo()
        if dispatch.sample_test_ids.result_ids:
            raise UserError(self.env._("A dispatch whose sample tests have results cannot be cancelled."))
        dispatch.write({"status": "cancelled", "failure_reason": reason.strip()})
        dispatch._notify_heads(
            EVENT_DISPATCH_DELIVERY_FAILED,
            "delivery_failed",
            self.env._(
                "The delivery of %(dispatch)s to %(subcontractor)s failed: %(reason)s Its sample tests stay outsourced; "
                "ask for the samples again and put them in a new dispatch.",
                dispatch=dispatch.code,
                subcontractor=dispatch.subcontractor_id.name,
                reason=reason.strip(),
            ),
        )

    def _portal_confirm_receipt(self):
        """The subcontractor's person confirms the samples of the sent dispatch arrived; the heads are told."""
        self.ensure_one()
        if self.status != "sent":
            raise UserError(self.env._("Only a sent dispatch can be received."))
        dispatch = self.sudo()
        dispatch.write({"status": "received", "received_date": fields.Date.context_today(self)})
        dispatch._notify_heads(
            EVENT_DISPATCH_RECEIVED,
            "received",
            self.env._(
                "%(subcontractor)s confirmed receipt of %(dispatch)s; it can enter the results.",
                subcontractor=dispatch.subcontractor_id.name,
                dispatch=dispatch.code,
            ),
        )

    def _heads(self):
        """The users who head the departments that test the dispatch's sample tests."""
        departments = self.env[MODEL_DEPARTMENT].union(
            *(test._testing_task().department_id for test in self.sudo().sample_test_ids)
        )
        return departments.manager_id.user_id.partner_id - self.env.user.partner_id

    def _notify_heads(self, event, kind, body):
        self.ensure_one()
        self.env[MODEL_MAIL_MESSAGE].raise_event(
            event, self, f"subcontract_dispatch:{self.id}:{kind}", body, subject=self.code, partners=self._heads()
        )
