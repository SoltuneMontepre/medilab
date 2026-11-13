from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import format_date

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_MACHINE_SERVICE,
    MODEL_PERMISSION_MIXIN,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_machine_service as MachineServiceBase
else:
    MachineServiceBase = object

# Fields that change when the machine can be booked: its calibration validity and the downtime of its services.
SCHEDULING_FIELDS = {"machine_id", "kind", "service_date", "next_due_date", "downtime_start", "downtime_end"}


# Lịch Sử Bảo Trì Máy
class MachineService(models.Model, MachineServiceBase):
    _name = MODEL_MACHINE_SERVICE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Machine Service"
    _order = "service_date desc, id desc"
    _permission_actions = ("create", "edit", "delete")

    if not TYPE_CHECKING:
        # The machine serviced.
        machine_id = fields.Many2one(MODEL_MACHINE, required=True, ondelete="restrict")
        # Whether the service was a calibration, a maintenance or a repair.
        kind = fields.Selection(
            [("calibration", "Calibration"), ("maintenance", "Maintenance"), ("repair", "Repair")], required=True
        )
        # Date the service was done; empty while it is planned.
        service_date = fields.Date(help="Leave empty while the service is planned.")
        # Start of the time the service takes the machine out of use; a planned maintenance reserves it, so no booking
        # overlaps it.
        downtime_start = fields.Datetime()
        # End of the time the service takes the machine out of use.
        downtime_end = fields.Datetime()
        # Date the next service of this kind is due, such as the calibration certificate's expiry.
        next_due_date = fields.Date()
        # Person or company that did the service.
        performed_by = fields.Char()
        # Number of the calibration certificate or service report.
        reference = fields.Char()
        # What was done and found.
        note = fields.Text()

    _machine_kind_date_index = models.Index("(machine_id, kind, service_date)")
    _machine_downtime_index = models.Index("(machine_id, downtime_start)")
    _downtime_period = models.Constraint(
        "CHECK((downtime_start IS NULL AND downtime_end IS NULL) OR downtime_end > downtime_start)",
        "A downtime has a start and an end after it.",
    )

    @api.depends("machine_id", "kind", "service_date")
    def _compute_display_name(self):
        kinds = dict(self._fields["kind"]._description_selection(self.env))
        for service in self:
            parts = [
                service.machine_id.code,
                kinds.get(service.kind or ""),
                format_date(self.env, service.service_date) if service.service_date else self.env._("Planned"),
            ]
            service.display_name = " – ".join(part for part in parts if part)

    @api.model_create_multi
    def create(self, vals_list):
        services = super().create(vals_list)
        self._requeue_bookings(services._scheduling_machines())
        return services

    def write(self, vals):
        machines = self._scheduling_machines()
        result = super().write(vals)
        if SCHEDULING_FIELDS & set(vals):
            self._requeue_bookings(machines | self._scheduling_machines())
        return result

    def unlink(self):
        machines = self._scheduling_machines()
        result = super().unlink()
        self._requeue_bookings(machines)
        return result

    def _scheduling_machines(self):
        return self.filtered(lambda service: service.kind == "calibration" or service.downtime_start).machine_id

    @api.model
    def _requeue_bookings(self, machines):
        # A calibration record can bring the calibration due date forward, past which the machine takes no bookings,
        # and a downtime takes the machine from the bookings it overlaps.
        if machines:
            self.env[MODEL_MACHINE_BOOKING]._requeue(machines)

    def _in_use_domain(self):
        # Service records are history and never keep a machine in use.
        return Domain.FALSE
