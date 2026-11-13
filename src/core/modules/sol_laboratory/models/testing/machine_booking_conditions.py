from datetime import timedelta
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import format_date

from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING, MODEL_RES_CONFIG_SETTINGS
from odoo.addons.sol_laboratory.services.type_values import value_as

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_machine_booking as MachineBookingConditionsBase
else:
    MachineBookingConditionsBase = object


# Lịch Đặt Máy: a machine is booked only while it is in use, calibrated, not overdue for maintenance and not down.
class MachineBookingConditions(models.Model, MachineBookingConditionsBase):
    _inherit = MODEL_MACHINE_BOOKING

    if not TYPE_CHECKING:
        # Why the tester should check the machine first: its calibration ends or its maintenance is due soon after
        # the booking, it was repaired shortly before, the booking's end passed or another booking still holds the
        # machine past its end; empty when nothing is due.
        machine_warning = fields.Text(compute="_compute_machine_warning")

    @api.depends("machine_id", "starts_at", "ends_at", "status")
    def _compute_machine_warning(self):
        settings = self.env[MODEL_RES_CONFIG_SETTINGS]
        windows = {
            name: timedelta(days=value_as(settings._get_parameter(name), int))
            for name in ("calibration_warning_days", "maintenance_warning_days", "repair_warning_days")
        }
        now = fields.Datetime.now()
        # The measurements past their end that still hold the machines of the bookings.
        held = self.sudo().search(
            [("machine_id", "in", self.machine_id.ids), ("status", "=", "in_progress"), ("ends_at", "<=", now)]
        )
        for booking in self:
            machine = booking.machine_id.sudo()
            start, end = booking.starts_at, booking.ends_at
            warnings = []
            if machine and start and end:
                if (
                    machine.next_calibration_date
                    and end > machine._usable_until() - windows["calibration_warning_days"]
                ):
                    warnings.append(
                        self.env._(
                            "The calibration of %(machine)s ends on %(date)s.",
                            machine=machine.display_name,
                            date=format_date(self.env, machine.next_calibration_date),
                        )
                    )
                due = machine._maintenance_due_end()
                if due and end > due - windows["maintenance_warning_days"]:
                    warnings.append(
                        self.env._(
                            "The maintenance of %(machine)s is due on %(date)s.",
                            machine=machine.display_name,
                            date=format_date(self.env, machine.next_maintenance_date),
                        )
                    )
                repair = machine._done_services().filtered(lambda service: service.kind == "repair")[:1]
                if repair and start < machine._day_end(repair.service_date) + windows["repair_warning_days"]:
                    warnings.append(
                        self.env._(
                            "%(machine)s was repaired on %(date)s.",
                            machine=machine.display_name,
                            date=format_date(self.env, repair.service_date),
                        )
                    )
                if booking.status in ("scheduled", "in_progress") and end <= now:
                    warnings.append(
                        self.env._(
                            "The booking's end has passed: enter its result or mark the measurement finished to free "
                            "%s.",
                            machine.display_name,
                        )
                    )
                elif booking.status == "scheduled" and (
                    holders := held.filtered(lambda other: other.machine_id == machine)
                ):
                    warnings.append(
                        self.env._(
                            "At risk: %(holder)s still holds %(machine)s past its end.",
                            holder=holders[:1].display_name,
                            machine=machine.display_name,
                        )
                    )
            booking.machine_warning = "\n".join(warnings) or False

    @api.constrains("status", "starts_at", "ends_at", "machine_id")
    def _check_machine_conditions(self):
        for booking in self.filtered(lambda booking: booking.status == "scheduled" and bool(booking.machine_id)):
            refusal = booking._machine_refusal(booking.machine_id.sudo(), booking.starts_at, booking.ends_at)
            if refusal:
                raise ValidationError(refusal)

    def _machine_refusal(self, machine, start, end):
        """Why the machine cannot be booked from start to end, or False when it can."""
        if not start or not end:
            return False
        if machine.status != "in_use" or not machine.active:
            return self.env._("%s is not in use.", machine.display_name)
        if end > machine._usable_until():
            return self.env._(
                "%s has no valid calibration until the end of the booking; record a calibration first.",
                machine.display_name,
            )
        due = machine._maintenance_due_end()
        if due and due <= fields.Datetime.now():
            return self.env._(
                "The maintenance of %(machine)s was due on %(date)s; record it before booking the machine.",
                machine=machine.display_name,
                date=format_date(self.env, machine.next_maintenance_date),
            )
        if machine._downtimes(start, end):
            return self.env._("%s is out of use for a planned service at that time.", machine.display_name)
        return False

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
        """The free slot, on a machine not overdue for maintenance, not held by a measurement past its end and after the
        downtime of its services."""
        if machine:
            now = fields.Datetime.now()
            due = machine.sudo()._maintenance_due_end()
            if due and due <= now:
                return None
            # A measurement whose end passed holds its machine until its result is entered or it is marked finished.
            held = self.sudo().search_count(
                [
                    ("machine_id", "=", machine.id),
                    ("status", "=", "in_progress"),
                    ("ends_at", "<=", now),
                    ("id", "not in", ignore.ids if ignore else []),
                ],
                limit=1,
            )
            if held:
                return None
        while True:
            start = super()._free_slot(
                machine, length, person, not_after, not_before, ignore, working, rooms, way, sample
            )
            if not start or not machine:
                return start
            downtimes = machine.sudo()._downtimes(start, start + length)
            if not downtimes:
                return start
            not_before = max(downtimes.mapped("downtime_end"))

    @api.model
    def _requeue(self, machines):
        """Also put the scheduled bookings that overlap a downtime of their machine back in the queue."""
        for machine in machines.sudo():
            if not machine.service_ids.filtered("downtime_start"):
                continue
            bookings = self.sudo().search(
                [("machine_id", "=", machine.id), ("status", "=", "scheduled"), ("ends_at", "!=", False)]
            )
            bookings.filtered(
                lambda booking, machine=machine: bool(machine._downtimes(booking.starts_at, booking.ends_at))
            )._set({"status": "queued", "starts_at": False, "ends_at": False})
        return super()._requeue(machines)
