from datetime import datetime
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import format_datetime

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LOCATION_UNAVAILABILITY,
    MODEL_MACHINE_BOOKING,
    MODEL_MACHINE_METHOD,
    MODEL_MAIL_MESSAGE,
    MODEL_TEST_RESULT,
)
from odoo.addons.sol_laboratory.constants.notifications import (
    EVENT_MACHINE_BOOKING_RETURNED,
    EVENT_TEST_RESULT_INTERRUPTED,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_machine_booking as MachineBookingInterruptionsBase
else:
    MachineBookingInterruptionsBase = object


# Lịch Đặt Máy: leave, an unavailable room and a machine failure interrupt bookings; a retest keeps its method.
class MachineBookingInterruptions(models.Model, MachineBookingInterruptionsBase):
    _inherit = MODEL_MACHINE_BOOKING

    @api.constrains("status", "machine_id", "method_id")
    def _check_retest_machine(self):
        links = self.env[MODEL_MACHINE_METHOD].sudo()
        for booking in self.filtered(lambda booking: booking.status == "scheduled" and bool(booking.machine_id)):
            earlier = booking.sudo().sample_test_id.result_ids.booking_id - booking
            if earlier and (
                booking.method_id not in earlier.method_id
                or not links.search_count(
                    [("machine_id", "=", booking.machine_id.id), ("method_id", "=", booking.method_id.id)], limit=1
                )
            ):
                raise ValidationError(
                    self.env._(
                        "A retest of %(booking)s runs by %(method)s, only on a machine linked to it.",
                        booking=booking.display_name,
                        method=earlier.method_id[:1].display_name,
                    )
                )

    @api.model
    def _free_slot(
        self,
        machine,
        length,
        person,
        not_after,
        not_before=None,
        ignore=None,
        working=None,
        rooms=(),
        way=None,
        sample=None,
    ):
        """The free slot, with the room of each step usable for the step's time."""
        closures = (
            self.env[MODEL_LOCATION_UNAVAILABILITY]
            .sudo()
            .search(
                [
                    ("location_id", "in", [step.location_id.id for step, _offset, _length in rooms]),
                    ("ends_at", ">", fields.Datetime.now()),
                ]
            )
        )
        while True:
            start = super()._free_slot(
                machine, length, person, not_after, not_before, ignore, working, rooms, way, sample
            )
            if not start:
                return start
            ends = [
                closure.ends_at - offset
                for step, offset, step_length in rooms
                for closure in closures
                if closure.location_id == step.location_id
                and closure.starts_at
                and closure.ends_at
                and closure.starts_at < start + offset + step_length
                and closure.ends_at > start + offset
            ]
            if not ends:
                return start
            not_before = max(ends)

    @api.model
    def _requeue(self, machines):
        """Also end the measurements in progress on a machine that can no longer finish them: it broke down or lost
        its calibration."""
        result = super()._requeue(machines)
        self.sudo().search([("machine_id", "in", machines.ids), ("status", "=", "in_progress")]).filtered(
            lambda booking: bool(booking.ends_at and booking.ends_at > booking.machine_id._usable_until())
        )._interrupt()
        return result

    def _interrupt(self):
        """End each measurement with an interrupted result, which keeps the data recorded so far for the head of
        department to assess, and tell its tester and head."""
        for booking in self:
            vals = {"sample_test_id": booking.sample_test_id.id, "is_interrupted": True}
            if booking.person_id.user_id:
                vals["entered_by_id"] = booking.person_id.user_id.id
            # Entering the result ends the booking and frees the machine.
            result = self.env[MODEL_TEST_RESULT].sudo().create(vals)
            self.env[MODEL_MAIL_MESSAGE].raise_event(
                EVENT_TEST_RESULT_INTERRUPTED,
                result,
                f"test_result:{result.id}:interrupted",
                self.env._(
                    "%(machine)s stopped during %(booking)s, so its measurement ended. Record the data measured so "
                    "far on the interrupted result, which the head of department assesses as usable, needing a retest "
                    "or needing more sample.",
                    machine=booking.machine_id.display_name,
                    booking=booking.display_name,
                ),
                subject=result.display_name,
                partners=booking.person_id.user_id.partner_id | booking.department_id.manager_id.user_id.partner_id,
            )

    def _return_to_plan(self, reason):
        """Put the scheduled bookings back in the queue for a new slot, and tell the head of each one's department why;
        nobody else is assigned."""
        if not self:
            return
        zone = self.env.company.tz or "UTC"
        starts = {booking: booking.starts_at for booking in self}
        self._set({"status": "queued", "starts_at": False, "ends_at": False})
        self._process_queue()
        for booking in self:
            body = self.env._(
                "%(booking)s, planned from %(start)s, went back to the plan. %(reason)s",
                booking=booking.display_name,
                start=format_datetime(self.env, starts[booking], tz=zone),
                reason=reason,
            )
            planned = booking.starts_at
            body += " " + (
                self.env._("It is now planned from %s.", format_datetime(self.env, planned, tz=zone))
                if isinstance(planned, datetime)
                else self.env._("No free slot finishes it by its due date.")
            )
            self.env[MODEL_MAIL_MESSAGE].raise_event(
                EVENT_MACHINE_BOOKING_RETURNED,
                booking,
                f"machine_booking:{booking.id}:{starts[booking]}:returned",
                body,
                subject=booking.display_name,
                partners=booking.department_id.manager_id.user_id.partner_id,
            )
