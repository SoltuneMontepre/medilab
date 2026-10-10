from odoo import api, fields, models
from odoo.fields import Domain

from odoo.addons.commerce.constants.models import MODEL_SERVICE_PACKAGE, MODEL_SERVICE_PACKAGE_LINE
from odoo.addons.laboratory.constants.models import MODEL_PERMISSION_MIXIN, MODEL_TEST_PARAMETER


# Links a service package to a parameter it includes, with how many times.
class ServicePackageLine(models.Model):
    _name = MODEL_SERVICE_PACKAGE_LINE
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Service Package Line"
    _order = "package_id, id"

    # The package.
    package_id = fields.Many2one(MODEL_SERVICE_PACKAGE, required=True, ondelete="cascade")
    # A parameter the package includes.
    parameter_id = fields.Many2one(MODEL_TEST_PARAMETER, required=True, ondelete="restrict", index=True)
    # How many times the package includes the parameter; at least 1.
    quantity = fields.Integer(required=True, default=1)

    _package_parameter_unique = models.Constraint(
        "UNIQUE(package_id, parameter_id)", "A package holds each parameter once; raise its quantity instead."
    )
    _quantity_positive = models.Constraint("CHECK(quantity >= 1)", "A package includes a parameter at least once.")

    @api.depends("package_id", "parameter_id")
    def _compute_display_name(self):
        for line in self:
            line.display_name = f"{line.package_id.name} – {line.parameter_id.name}"

    @api.model_create_multi
    def create(self, vals_list):
        # A parameter the package already holds raises that line's quantity instead of taking a second line.
        lines = self.browse()
        for vals in vals_list:
            line = self.search(
                Domain("package_id", "=", vals.get("package_id"))
                & Domain("parameter_id", "=", vals.get("parameter_id")),
                limit=1,
            )
            if line:
                line.quantity += vals.get("quantity", 1)
            else:
                line = super().create([vals])
            lines += line
        return lines

    def _in_use_domain(self):
        # A line keeps its parameter in use while its package is active.
        return Domain("package_id.active", "=", True)
