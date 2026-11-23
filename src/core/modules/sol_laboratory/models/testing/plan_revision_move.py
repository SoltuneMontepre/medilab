from typing import TYPE_CHECKING

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import format_datetime

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_DEPARTMENT,
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_MAIL_MESSAGE,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_PLAN_REVISION,
    MODEL_PLAN_REVISION_MOVE,
)
from odoo.addons.sol_laboratory.constants.notifications import EVENT_MACHINE_BOOKING_MOVED
from odoo.addons.sol_laboratory.models.testing.machine_booking import _rooms_end

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_plan_revision_move as PlanRevisionMoveBase
else:
    PlanRevisionMoveBase = object


# Lịch Đặt Được Dời
class PlanRevisionMove(models.Model, PlanRevisionMoveBase):
    _name = MODEL_PLAN_REVISION_MOVE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Plan Revision Move"
    _order = "revision_id desc, starts_at, id"
    _rec_name = "booking_id"
    # Moves are proposed by the scheduler and decided through their revision.
    _permission_actions = ("read",)

    if not TYPE_CHECKING:
        # The plan revision.
        revision_id = fields.Many2one(MODEL_PLAN_REVISION, required=True, ondelete="cascade", index=True, readonly=True)
        # The scheduled booking moved.
        booking_id = fields.Many2one(
            MODEL_MACHINE_BOOKING, required=True, ondelete="restrict", index=True, readonly=True
        )
        # The department of the booking, whose head approves the move.
        department_id = fields.Many2one(MODEL_DEPARTMENT, required=True, ondelete="restrict", index=True, readonly=True)
        # The machine the booking moves to, one linked to the same method; empty when the way needs no machine.
        machine_id = fields.Many2one(MODEL_MACHINE, ondelete="restrict", readonly=True)
        # Start of the slot the booking leaves.
        previous_starts_at = fields.Datetime(string="Previous Start", readonly=True)
        # End of the slot the booking leaves.
        previous_ends_at = fields.Datetime(string="Previous End", readonly=True)
        # New start of the booking.
        starts_at = fields.Datetime(string="New Start", required=True, readonly=True)
        # New end of the booking.
        ends_at = fields.Datetime(string="New End", required=True, readonly=True)
        # Proposed until the head of its department approves it, then approved and applied with its revision. Held back
        # when it would finish after the sample test's internal due date: the booking keeps its slot until Sales records
        # the customer's agreement to a new committed return date. In conflict when it would move a pinned booking,
        # which no revision moves.
        status = fields.Selection(
            [
                ("proposed", "Proposed"),
                ("approved", "Approved"),
                ("held_back", "Held Back"),
                ("conflict", "Conflict"),
                ("applied", "Applied"),
            ],
            required=True,
            default="proposed",
            readonly=True,
            index=True,
        )
        # The head of department who approved the move.
        approved_by_id = fields.Many2one(MODEL_PERSON, string="Approved By", ondelete="restrict", readonly=True)
        # The sample test of the booking.
        sample_test_id = fields.Many2one(related="booking_id.sample_test_id")
        # The tester of the booking.
        person_id = fields.Many2one(related="booking_id.person_id")
        # The internal due date of the sample test.
        due_date = fields.Datetime(related="booking_id.sample_test_id.due_date")
        # The committed return date Sales promised the customer.
        committed_date = fields.Date(related="booking_id.sample_test_id.sample_id.request_id.committed_date")

    _revision_booking_unique = models.Constraint(
        "UNIQUE(revision_id, booking_id)", "A plan revision moves a booking once."
    )
    _booking_status_idx = models.Index("(booking_id, status)")
    _department_status_idx = models.Index("(department_id, status)")
    _slot_period = models.Constraint("CHECK(ends_at > starts_at)", "A booking ends after it starts.")

    def _of_my_departments(self):
        """The moves whose booking the current user may edit: those of the departments they head."""
        bookings = self.env[MODEL_MACHINE_BOOKING]
        if self.env.su or "all" in bookings._user_scopes("edit"):
            return self
        wanted = self.sudo().booking_id
        allowed = bookings.sudo().search(Domain("id", "in", wanted.ids) & bookings._permission_domain("edit"))
        return self.filtered(lambda move: move.sudo().booking_id in allowed)

    def _apply(self):
        """Move the bookings of the moves to their new slots together: all leave their slots first, since the new slot of
        one may be the old slot of another. A booking that is no longer scheduled, or whose new slot was taken
        meanwhile, refuses the whole revision."""
        bookings = self.env[MODEL_MACHINE_BOOKING].sudo()
        now = fields.Datetime.now()
        moves = self.sudo().sorted("starts_at")
        leaving = moves.booking_id
        planned = bookings.browse()
        for move in moves:
            booking = move.booking_id
            way = booking.sample_test_id.parameter_method_id
            rooms = bookings._room_steps(way)
            move_start = move.starts_at
            move_end = move.ends_at
            slot = None
            start = booking.starts_at
            if (
                move_start
                and move_end
                and booking.status == "scheduled"
                and not booking.is_pinned
                and start
                and start > now
            ):
                length = move_end - move_start
                slot = bookings._free_slot(
                    move.machine_id,
                    length,
                    booking.person_id,
                    move_start + max(length, _rooms_end(rooms)),
                    move_start,
                    leaving,
                    rooms=rooms,
                    way=way,
                    sample=booking.sample_test_id.sample_id,
                    planned=planned,
                )
            if slot != move.starts_at:
                raise UserError(
                    self.env._(
                        "The new slot of %s was taken meanwhile; open the plan revisions again for the recalculation.",
                        booking.display_name,
                    )
                )
            planned |= bookings.new(
                booking._simulation_values(move.machine_id, booking.method_id, move.starts_at, move.ends_at)
            )
        leaving._set({"status": "proposed", "starts_at": False, "ends_at": False})
        for move in moves:
            move.booking_id._set(
                {
                    "machine_id": move.machine_id.id,
                    "starts_at": move.starts_at,
                    "ends_at": move.ends_at,
                    "status": "scheduled",
                }
            )
        moves.write({"status": "applied"})

    def _notify_moved(self):
        """Tell the tester of each moved booking where it moved to."""
        zone = self.env.company.tz or "UTC"
        stamp = fields.Datetime.to_string(fields.Datetime.now())
        for move in self.sudo():
            booking = move.booking_id
            tester = booking.person_id.user_id
            if not tester or tester == self.env.user:
                continue
            self.env[MODEL_MAIL_MESSAGE].raise_event(
                EVENT_MACHINE_BOOKING_MOVED,
                booking,
                f"machine_booking:{booking.id}:{tester.id}:{stamp}:moved",
                self.env._(
                    "%(booking)s moved from %(old)s to %(new)s.",
                    booking=booking.display_name,
                    old=format_datetime(self.env, move.previous_starts_at or move.starts_at, tz=zone),
                    new=format_datetime(self.env, move.starts_at, tz=zone),
                ),
                subject=booking.display_name,
                partners=tester.partner_id,
            )
