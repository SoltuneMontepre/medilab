from datetime import timedelta

from odoo import api, fields, models

from odoo.addons.laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_MACHINE,
    MODEL_MACHINE_SERVICE,
    MODEL_PARAMETER_METHOD_MACHINE,
)


# Máy
class Machine(models.Model):
    _name = MODEL_MACHINE
    _inherit = [MODEL_ARCHIVE_MIXIN]
    _description = "Machine"
    _order = "code"
    _rec_names_search = ["name", "code", "serial_number"]

    # Unique code of the machine.
    code = fields.Char(required=True, copy=False)
    # Name of the machine, such as "HPLC 1".
    name = fields.Char(required=True)
    # Model of the machine, as named by the manufacturer.
    model = fields.Char()
    # Company that made the machine.
    manufacturer = fields.Char()
    # Serial number given by the manufacturer.
    serial_number = fields.Char()
    # Where the machine is, such as "Room 203, bench 2".
    location = fields.Char()
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
    # Parameter and method pairs the machine can run, with the run time of each.
    parameter_method_ids = fields.One2many(MODEL_PARAMETER_METHOD_MACHINE, "machine_id", string="Ways of Testing")
    # False when the machine is archived.
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a machine must be unique.")

    @api.depends(
        "service_ids.kind", "service_ids.service_date", "service_ids.next_due_date", "maintenance_interval_days"
    )
    def _compute_next_service_dates(self):
        for machine in self:
            services = machine.service_ids.sorted("service_date", reverse=True)
            calibration = services.filtered(lambda service: service.kind == "calibration")[:1]
            maintenance = services.filtered(lambda service: service.kind == "maintenance")[:1]
            machine.next_calibration_date = calibration.next_due_date
            machine.next_maintenance_date = (
                maintenance.service_date + timedelta(days=machine.maintenance_interval_days)
                if maintenance and machine.maintenance_interval_days
                else False
            )
