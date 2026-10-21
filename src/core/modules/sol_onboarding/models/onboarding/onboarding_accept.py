from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.departments import DEPARTMENT_DOMAIN
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DEPARTMENT,
    MODEL_MEASUREMENT_UNIT,
    MODEL_PARAMETER_GROUP,
    MODEL_TESTING_FIELD,
)
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_ACCEPT, MODEL_ONBOARDING_STAGED_RECORD


# Chấp Nhận Bản Ghi Chờ Duyệt
class OnboardingAccept(models.TransientModel):
    _name = MODEL_ONBOARDING_ACCEPT
    _description = "Accept Staged Record"

    # The staged record to accept.
    staged_record_id = fields.Many2one(
        MODEL_ONBOARDING_STAGED_RECORD, string="Staged Record", required=True, ondelete="cascade"
    )
    # Code of the testing field to create.
    code = fields.Char(string="Code")
    # Testing field of the testing method to create.
    field_id = fields.Many2one(MODEL_TESTING_FIELD, string="Testing Field")
    # Main group of the test parameter to create.
    main_group_id = fields.Many2one(MODEL_PARAMETER_GROUP, string="Main Group", domain="[('child_ids', '=', False)]")
    # Unit of the way of testing to create.
    unit_id = fields.Many2one(MODEL_MEASUREMENT_UNIT, string="Unit")
    # Department that tests the way of testing to create.
    department_id = fields.Many2one(MODEL_DEPARTMENT, string="Department", domain=DEPARTMENT_DOMAIN)
    # True when the staged record misses the code.
    code_needed = fields.Boolean(string="Code Needed", compute="_compute_needed")
    # True when the staged record misses the testing field.
    field_needed = fields.Boolean(string="Testing Field Needed", compute="_compute_needed")
    # True when the staged record misses the main group.
    main_group_needed = fields.Boolean(string="Main Group Needed", compute="_compute_needed")
    # True when the staged record misses the unit.
    unit_needed = fields.Boolean(string="Unit Needed", compute="_compute_needed")
    # True when the staged record misses the department.
    department_needed = fields.Boolean(string="Department Needed", compute="_compute_needed")

    @api.depends("staged_record_id")
    def _compute_needed(self):
        for wizard in self:
            missing = wizard.staged_record_id._missing_values() if wizard.staged_record_id else []
            wizard.code_needed = "code" in missing
            wizard.field_needed = "field_id" in missing
            wizard.main_group_needed = "main_group_id" in missing
            wizard.unit_needed = "unit_id" in missing
            wizard.department_needed = "department_id" in missing

    def action_confirm(self):
        self.ensure_one()
        staged = self.staged_record_id
        staged.write({key: self[key] for key in staged._missing_values()})
        return staged.action_accept()
