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

CALIBRATION_FIELDS = {"machine_id", "kind", "service_date", "next_due_date"}


# Lịch Sử Bảo Trì Máy
class MachineService(models.Model):
    _name = MODEL_MACHINE_SERVICE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Machine Service"
    _order = "service_date desc, id desc"
    _permission_actions = ("create", "edit", "delete")

    # The machine serviced.
    machine_id = fields.Many2one(MODEL_MACHINE, required=True, ondelete="restrict")
    # Whether the service was a calibration, a maintenance or a repair.
    kind = fields.Selection(
        [("calibration", "Calibration"), ("maintenance", "Maintenance"), ("repair", "Repair")], required=True
    )
    # Date the service was done.
    service_date = fields.Date(required=True, default=fields.Date.context_today)
    # Date the next service of this kind is due, such as the calibration certificate's expiry.
    next_due_date = fields.Date()
    # Person or company that did the service.
    performed_by = fields.Char()
    # Number of the calibration certificate or service report.
    reference = fields.Char()
    # What was done and found.
    note = fields.Text()

    _machine_kind_date_index = models.Index("(machine_id, kind, service_date)")

    @api.depends("machine_id", "kind", "service_date")
    def _compute_display_name(self):
        kinds = dict(self._fields["kind"]._description_selection(self.env))
        for service in self:
            parts = [service.machine_id.code, kinds.get(service.kind), format_date(self.env, service.service_date)]
            service.display_name = " – ".join(part for part in parts if part)

    @api.model_create_multi
    def create(self, vals_list):
        services = super().create(vals_list)
        self._requeue_bookings(services._calibrated_machines())
        return services

    def write(self, vals):
        machines = self._calibrated_machines()
        result = super().write(vals)
        if CALIBRATION_FIELDS & set(vals):
            self._requeue_bookings(machines | self._calibrated_machines())
        return result

    def unlink(self):
        machines = self._calibrated_machines()
        result = super().unlink()
        self._requeue_bookings(machines)
        return result

    def _calibrated_machines(self):
        return self.filtered(lambda service: service.kind == "calibration").machine_id

    @api.model
    def _requeue_bookings(self, machines):
        # A calibration record can bring the calibration due date forward, past which the machine takes no bookings.
        if machines:
            self.env[MODEL_MACHINE_BOOKING]._requeue(machines)

    def _in_use_domain(self):
        # Service records are history and never keep a machine in use.
        return Domain.FALSE
