from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_inventory.constants.models import MODEL_ANALYTIC_ACCOUNT
from odoo.addons.sol_inventory.constants.xml_ids import COST_CENTRE_PLAN
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_DEPARTMENT,
    MODEL_PERMISSION_MIXIN,
)


# Trung Tâm Chi Phí
class AccountAnalyticAccount(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_ANALYTIC_ACCOUNT
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_ANALYTIC_ACCOUNT, MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN]

    # The department or team whose stock is charged to the cost centre.
    department_id = fields.Many2one(MODEL_DEPARTMENT, string="Department or Team", ondelete="restrict")

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a cost centre or analytic account must be unique.")
    _department_unique = models.Constraint(
        "UNIQUE(department_id)", "This department or team already has a cost centre."
    )

    @api.constrains("plan_id", "code", "department_id")
    def _check_cost_centre(self):
        plan = self.env.ref(COST_CENTRE_PLAN)
        for account in self.filtered(lambda account: account.plan_id == plan):
            if not account.code or not account.department_id:
                raise ValidationError(
                    self.env._("The cost centre %s needs a code and a department or team.", account.name)
                )
