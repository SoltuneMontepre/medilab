from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import SQL

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_MACHINE_METHOD,
    MODEL_PERMISSION_MIXIN,
    MODEL_TESTING_METHOD,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_machine_method as MachineMethodBase
else:
    MachineMethodBase = object


# Links testing methods to the machines that run them, with the booking duration and capacity.
class MachineMethod(models.Model, MachineMethodBase):
    _name = MODEL_MACHINE_METHOD
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Machine for a Testing Method"
    _order = "machine_id, id"
    _permission_actions = ("create", "edit", "delete")

    if not TYPE_CHECKING:
        # The machine.
        machine_id = fields.Many2one(MODEL_MACHINE, required=True, ondelete="restrict")
        # The testing method the machine runs; every way of testing that uses it can be booked on the machine.
        method_id = fields.Many2one(
            MODEL_TESTING_METHOD, required=True, ondelete="cascade", index=True, string="Testing Method"
        )
        # Minutes a booking of the method takes on the machine, covering preparation, measurement and time to repeat a
        # failed measurement; the booking rounds it up to whole slots.
        duration_minutes = fields.Integer(required=True, string="Duration (minutes)")
        # Samples one interval of the machine holds for bookings of the method; several parameters of one sample take
        # one place.
        capacity = fields.Integer(required=True, default=1)

    _machine_method_unique = models.Constraint(
        "UNIQUE(machine_id, method_id)", "The machine is already linked to this testing method."
    )
    _duration_positive = models.Constraint("CHECK(duration_minutes > 0)", "A booking takes at least one minute.")
    _capacity_positive = models.Constraint("CHECK(capacity >= 1)", "A machine holds at least one sample.")

    @api.depends("machine_id", "method_id")
    def _compute_display_name(self):
        for link in self:
            link.display_name = f"{link.machine_id.code} – {link.method_id.code}"

    def write(self, vals):
        if "capacity" in vals and self.machine_id:
            # Booking placement writes the same rows, so a concurrent capacity change retries with a fresh snapshot.
            self.env.cr.execute(
                SQL(
                    "UPDATE %s SET write_date = write_date WHERE id IN %s",
                    SQL.identifier(self.env[MODEL_MACHINE]._table),
                    tuple(self.machine_id.ids),
                )
            )
        return super().write(vals)

    @api.constrains("capacity")
    def _check_booked_capacity(self):
        for link in self:
            self.env[MODEL_MACHINE_BOOKING]._check_machine_method_capacity(link)

    def _in_use_domain(self):
        # A link keeps its machine in use while its testing method is active.
        return Domain("method_id.active", "=", True)
