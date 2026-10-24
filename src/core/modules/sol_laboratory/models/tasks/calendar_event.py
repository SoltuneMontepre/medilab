from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain
from odoo.tools import format_datetime

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_CALENDAR_EVENT,
    MODEL_LOCATION,
    MODEL_MACHINE_BOOKING,
    MODEL_TASK,
)
from odoo.addons.sol_laboratory.constants.xml_ids import ADMINISTRATOR_GROUP

SKIP_SYNC = "medilab_skip_calendar_sync"
# Fields that move a location booking or change the location it books.
BOOKING_FIELDS = frozenset({"start", "stop", "start_date", "stop_date", "allday", "duration", "location_id"})


# Lịch
class CalendarEvent(models.Model):
    _name = MODEL_CALENDAR_EVENT
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_CALENDAR_EVENT]

    # The planned task this event keeps in step with.
    medilab_task_id = fields.Many2one(MODEL_TASK, ondelete="cascade", index=True)
    # The machine booking whose slot the event shows.
    medilab_booking_ids = fields.One2many(MODEL_MACHINE_BOOKING, "calendar_event_id", string="Machine Bookings")
    # The bookable location the event books.
    location_id = fields.Many2one(
        MODEL_LOCATION,
        string="Booked Location",
        ondelete="restrict",
        index="btree_not_null",
        domain="[('is_bookable', '=', True)]",
    )

    _location_no_overlap = models.Constraint(
        "EXCLUDE USING gist (location_id WITH =, tsrange(start, stop) WITH &&, id WITH <>) "
        "WHERE (location_id IS NOT NULL AND active)",
        lambda env, diagnostics: env[MODEL_CALENDAR_EVENT]._overlap_message(diagnostics),
    )

    def _auto_init(self):
        # The overlap constraint compares locations with a GiST index, which needs btree_gist.
        self.env.cr.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        return super()._auto_init()

    @api.model
    def _overlap_message(self, diagnostics):
        # PostgreSQL ends the detail of an overlap with the id of the booking already there, as in "..., 12).".
        overlapped = (getattr(diagnostics, "message_detail", None) or "").rstrip(".)").rpartition(" ")[2]
        booking = self.browse(int(overlapped)).exists() if overlapped.isdigit() else self
        if not booking:
            return self.env._("The location is already booked at that time.")
        return self.env._(
            "%(location)s is already booked from %(start)s to %(stop)s: %(booking)s.",
            location=booking.location_id.display_name,
            start=format_datetime(self.env, booking.start),
            stop=format_datetime(self.env, booking.stop),
            booking=booking.display_name,
        )

    @api.depends("location_id", "user_id")
    def _compute_user_can_edit(self):
        super()._compute_user_can_edit()
        # The form leaves a location booking read-only to anyone but its organiser; an administrator opens it to cancel.
        if self.env.user.has_group(ADMINISTRATOR_GROUP):
            return
        for event in self.filtered("location_id"):
            event.user_can_edit = event.user_can_edit and event.user_id == self.env.user

    @api.constrains("location_id")
    def _check_location_bookable(self):
        for location in self.location_id:
            if not location.is_bookable or not location.active:
                raise ValidationError(self.env._("%s cannot be booked.", location.display_name))

    @api.model_create_multi
    def create(self, vals_list):
        booking = False
        for vals in vals_list:
            location_id = vals.get("location_id", self.env.context.get("default_location_id"))
            if location_id:
                booking = True
                vals.update(self._booking_values(location_id))
        if booking:
            self._flush_bookings()
        return super().create(vals_list)

    def write(self, vals):
        bookings = self if vals.get("location_id") else self.filtered("location_id")
        if bookings and BOOKING_FIELDS & set(vals):
            bookings._check_organiser()
            self._flush_bookings()
        if vals.get("active") is False:
            bookings._check_organiser(cancelling=True)
        if "location_id" in vals:
            vals = {**vals, **self._booking_values(vals["location_id"])}
        result = super().write(vals)
        if not self.env.context.get(SKIP_SYNC) and {"start", "stop"} & set(vals):
            self._copy_times_to_tasks()
            self._move_bookings()
        return result

    def _flush_bookings(self):
        # The overlap constraint checks each row as it is written, so bookings cancelled or moved earlier in the
        # transaction are written before a booking takes their slot.
        self.flush_model(["location_id", "start", "stop", "active"])

    def _booking_values(self, location_id):
        if not location_id:
            # An event that no longer books a location no longer names one.
            return {"location": False}
        # The reminder job reminds of a booking once, so the event has no Odoo alarm of its own.
        location = self.env[MODEL_LOCATION].browse(location_id)
        return {"alarm_ids": [Command.clear()], "location": location.display_name}

    def _check_organiser(self, cancelling=False):
        """The organiser moves or cancels a location booking; an administrator may also cancel it."""
        if self.env.su or (cancelling and self.env.user.has_group(ADMINISTRATOR_GROUP)):
            return
        others = self.filtered(lambda event: event.user_id != self.env.user)
        if others and cancelling:
            raise UserError(self.env._("Only the organiser or an administrator can cancel %s.", others[0].display_name))
        if others:
            raise UserError(self.env._("Only the organiser can change %s.", others[0].display_name))

    def _in_use_domain(self):
        # A booking keeps its location in use until it is over.
        return Domain("active", "=", True) & Domain("stop", ">", fields.Datetime.now())

    def _copy_times_to_tasks(self):
        for event in self.filtered("medilab_task_id"):
            event.medilab_task_id.with_context(**{SKIP_SYNC: True}).write(
                {"planned_start": event.start, "planned_end": event.stop}
            )

    def _move_bookings(self):
        # The booking moves only to a free slot, then puts the event back on its own times.
        for booking in self.sudo().medilab_booking_ids:
            booking.with_env(self.env)._move(booking.calendar_event_id.start)

    def unlink(self):
        self.filtered("location_id")._check_organiser(cancelling=True)
        tasks = self.medilab_task_id.with_context(**{SKIP_SYNC: True})
        result = super().unlink()
        tasks.write({"planned_start": False, "planned_end": False})
        return result
