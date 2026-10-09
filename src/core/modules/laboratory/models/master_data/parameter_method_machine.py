from odoo import api, fields, models
from odoo.fields import Domain

from odoo.addons.laboratory.constants.models import (
    MODEL_MACHINE,
    MODEL_PARAMETER_METHOD,
    MODEL_PARAMETER_METHOD_MACHINE,
)


# Links parameter and method pairs to the machines that can run them, with the run time.
class ParameterMethodMachine(models.Model):
    _name = MODEL_PARAMETER_METHOD_MACHINE
    _description = "Machine for a Way of Testing"
    _order = "machine_id, id"

    # The parameter and method pair.
    parameter_method_id = fields.Many2one(
        MODEL_PARAMETER_METHOD, required=True, ondelete="cascade", string="Way of Testing"
    )
    # A machine that can run it.
    machine_id = fields.Many2one(MODEL_MACHINE, required=True, ondelete="restrict", index=True)
    # Minutes one run takes on the machine; the booking rounds it up to whole slots.
    run_minutes = fields.Integer(required=True)

    _pair_machine_unique = models.Constraint(
        "UNIQUE(parameter_method_id, machine_id)", "The machine is already linked to this way of testing."
    )
    _run_minutes_positive = models.Constraint("CHECK(run_minutes > 0)", "A run takes at least one minute.")

    @api.depends("parameter_method_id", "machine_id")
    def _compute_display_name(self):
        for link in self:
            link.display_name = f"{link.machine_id.code} – {link.parameter_method_id.display_name}"

    def _in_use_domain(self):
        # A link keeps its machine in use while its way of testing is active.
        return Domain("parameter_method_id.active", "=", True)
