from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import format_date

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_LOCATION,
    MODEL_LOCK_MIXIN,
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_MACHINE_METHOD,
    MODEL_MACHINE_SERVICE,
    MODEL_PERMISSION_MIXIN,
    MODEL_SAMPLE,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_machine as MachineBase
else:
    MachineBase = object


# Máy
class Machine(models.Model, MachineBase):
    _name = MODEL_MACHINE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Machine"
    _order = "code"
    _rec_names_search = ("name", "code", "serial_number")
    _permission_actions = ("create", "edit", "archive", "delete")
    _audit_children = ("service_ids", "method_ids")

    if not TYPE_CHECKING:
        # Unique code of the machine.
        code = fields.Char(required=True, copy=False, index="trigram")
        # Name of the machine, such as "HPLC 1".
        name = fields.Char(required=True, index="trigram")
        # Model of the machine, as named by the manufacturer.
        model = fields.Char()
        # Company that made the machine.
        manufacturer = fields.Char()
        # Serial number given by the manufacturer.
        serial_number = fields.Char(index="trigram")
        # The location the machine stands in, such as a bench.
        location_id = fields.Many2one(MODEL_LOCATION, string="Location", ondelete="restrict", index=True)
        # Whether the machine is in use, under repair or retired.
        status = fields.Selection(
            [("in_use", "In use"), ("under_repair", "Under repair"), ("retired", "Retired")],
            required=True,
            default="in_use",
        )
        # Date the next calibration is due, taken from the latest calibration record; the machine cannot be used after it.
        next_calibration_date = fields.Date(compute="_compute_next_service_dates", store=True, index=True)
        # Days between two maintenance visits; empty when the machine has no schedule.
        maintenance_interval_days = fields.Integer()
        # Date the next maintenance is due, from the latest maintenance record and the interval.
        next_maintenance_date = fields.Date(compute="_compute_next_service_dates", store=True)
        # Calibration, maintenance and repair records of the machine.
        service_ids = fields.One2many(MODEL_MACHINE_SERVICE, "machine_id", string="Service History")
        # Testing methods the machine runs, with the booking duration and capacity of each.
        method_ids = fields.One2many(MODEL_MACHINE_METHOD, "machine_id", string="Testing Methods")
        # Bookings of the machine.
        booking_ids = fields.One2many(MODEL_MACHINE_BOOKING, "machine_id", string="Bookings")
        # False when the machine is archived.
        active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a machine must be unique.")

    @api.depends(
        "service_ids.kind", "service_ids.service_date", "service_ids.next_due_date", "maintenance_interval_days"
    )
    def _compute_next_service_dates(self):
        for machine in self:
            services = machine._done_services()
            calibration = services.filtered(lambda service: service.kind == "calibration")[:1]
            maintenance = services.filtered(lambda service: service.kind == "maintenance")[:1]
            machine.next_calibration_date = calibration.next_due_date
            machine.next_maintenance_date = (
                maintenance.service_date + timedelta(days=machine.maintenance_interval_days)
                if maintenance and maintenance.service_date and machine.maintenance_interval_days
                else False
            )

    @api.constrains("status")
    def _check_return_after_repair(self):
        for machine in self.filtered(lambda machine: machine.status == "in_use"):
            services = machine._done_services()
            repair = services.filtered(lambda service: service.kind == "repair")[:1]
            if repair and services[:1].kind == "repair":
                raise ValidationError(
                    self.env._(
                        "Record a calibration or maintenance of %(machine)s done after its repair on %(date)s before "
                        "putting it back in use.",
                        machine=machine.display_name,
                        date=format_date(self.env, repair.service_date),
                    )
                )

    def write(self, vals):
        result = super().write(vals)
        if {"status", "active"} & set(vals):
            self.env[MODEL_MACHINE_BOOKING]._requeue(self)
        return result

    def _done_services(self):
        """The services done, latest first; of one day, the one recorded last first."""
        self.ensure_one()
        return self.service_ids.filtered("service_date").sorted(
            lambda service: (service.service_date, service._origin.id or 0), reverse=True
        )

    def _usable_until(self):
        """When the machine stops being fit to use, as naive UTC: at the end of its calibration due date.

        A machine under repair, retired, archived or never calibrated is not fit to use at all.
        """
        self.ensure_one()
        if self.status != "in_use" or not self.active:
            return datetime.min
        if not self.next_calibration_date:
            calibrated = any(service.kind == "calibration" for service in self._done_services())
            return datetime.max if calibrated else datetime.min
        return self._day_end(self.next_calibration_date)

    def _maintenance_due_end(self):
        """When the machine's maintenance becomes overdue, as naive UTC: at the end of its due date; None without a
        maintenance schedule."""
        self.ensure_one()
        return self._day_end(self.next_maintenance_date) if self.next_maintenance_date else None

    def _day_end(self, day):
        return self.env[MODEL_SAMPLE]._company_datetime(day + timedelta(days=1), 0)

    def _downtimes(self, start, end):
        """The services whose downtime overlaps start to end."""
        self.ensure_one()
        return self.service_ids.filtered(
            lambda service: bool(
                service.downtime_start
                and service.downtime_end
                and service.downtime_start < end
                and service.downtime_end > start
            )
        )
