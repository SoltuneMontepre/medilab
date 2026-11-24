from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_datetime

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE_BOOKING,
    MODEL_MAIL_MESSAGE,
    MODEL_PARAMETER_AUTHORIZATION,
)
from odoo.addons.sol_laboratory.constants.notifications import EVENT_MACHINE_BOOKING_APPROVED
from odoo.addons.sol_laboratory.models.testing.machine_booking import _rooms_end

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_machine_booking as MachineBookingApprovalBase
else:
    MachineBookingApprovalBase = object


# Lịch Đặt Máy: the head of department approves a feasible proposed booking, which reserves it.
class MachineBookingApproval(models.Model, MachineBookingApprovalBase):
    _inherit = MODEL_MACHINE_BOOKING

    @api.model_create_multi
    def create(self, vals_list):
        # Scheduling creates its bookings as superuser; nobody else makes one that is not proposed.
        if not self.env.su and any(vals.get("status", "proposed") != "proposed" for vals in vals_list):
            raise UserError(self._approval_required())
        return super().create(vals_list)

    def write(self, vals):
        # A booking changes status through its actions, which check what the change needs.
        if not self.env.su and "status" in vals:
            raise UserError(self._approval_required())
        return super().write(vals)

    def _approval_required(self):
        return self.env._("A booking is reserved only when the head of the department approves it.")

    def _proposed_slot_is_available(self):
        self.ensure_one()
        start, end = self.starts_at, self.ends_at
        if not start or not end:
            return False
        test = self.sudo().sample_test_id
        way = self._proposed_way()
        rooms = self._room_steps(way)
        length = end - start
        planned = self.sudo().search(
            [
                ("department_id", "=", self.sudo().department_id.id),
                ("status", "=", "proposed"),
                ("id", "!=", self.id),
                ("starts_at", "!=", False),
            ]
        )
        slot = self._free_slot(
            self.machine_id,
            length,
            self.person_id,
            start + max(length, _rooms_end(rooms)),
            start,
            self,
            rooms=rooms,
            way=way,
            sample=test.sample_id,
            planned=planned,
        )
        return slot == start

    def action_approve(self):
        """Approve a proposed slot when its tester, machine and rooms are still free, then tell the tester."""
        self._check_permission("edit")
        for booking in self:
            if booking.status != "proposed":
                raise UserError(self.env._("Only a proposed booking can be approved."))
            if not booking.person_id:
                raise UserError(self.env._("Assign %s to a tester before approving its booking.", booking.display_name))
            start, end = booking.starts_at, booking.ends_at
            if not start or not end:
                raise UserError(self.env._("No machine can finish %s before its due date.", booking.display_name))
            test = booking.sudo().sample_test_id
            test._check_bookable()
            self.env[MODEL_PARAMETER_AUTHORIZATION]._check_authorized(booking.person_id, test.parameter_id)
            way = booking._proposed_way()
            if test.parameter_method_id != way:
                # The way's steps give the rooms the booking books.
                test.parameter_method_id = way
            if not booking._proposed_slot_is_available():
                raise UserError(
                    self.env._(
                        "The slot of %s was taken meanwhile; open the plan again for its new slot.",
                        booking.display_name,
                    )
                )
            booking._set({"status": "scheduled"})
        self._notify_approved()

    def _notify_approved(self):
        """Tell each booking's tester that the head approved it, unless the tester approved it themselves."""
        zone = self.env.company.tz or "UTC"
        stamp = fields.Datetime.to_string(fields.Datetime.now())
        for booking in self.sudo():
            tester, start = booking.person_id.user_id, booking.starts_at
            if not tester or not start or tester == self.env.user:
                continue
            self.env[MODEL_MAIL_MESSAGE].raise_event(
                EVENT_MACHINE_BOOKING_APPROVED,
                booking,
                f"machine_booking:{booking.id}:{tester.id}:{stamp}:approved",
                self.env._(
                    "%(booking)s is approved: it starts at %(start)s.",
                    booking=booking.display_name,
                    start=format_datetime(self.env, start, tz=zone),
                ),
                subject=booking.display_name,
                partners=tester.partner_id,
            )
