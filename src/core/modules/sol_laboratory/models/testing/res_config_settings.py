from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.tools import clean_context

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS, MODEL_ROLE
from odoo.addons.sol_laboratory.constants.settings import (
    DEFAULT_REMINDER_LEAD_MINUTES,
    DEFAULT_SAFETY_MARGIN_DAYS,
    DEFAULT_SAMPLE_RETENTION_REMINDER_DAYS,
    DEFAULT_URGENCY_HOURS,
    REMINDER_LEAD_PARAMETER,
    SAFETY_MARGIN_PARAMETER,
    SAMPLE_DELIVERY_ROLE_PARAMETER,
    SAMPLE_RETENTION_REMINDER_PARAMETER,
    URGENCY_HOURS_PARAMETER,
)
from odoo.addons.sol_laboratory.services.type_values import value_as

if TYPE_CHECKING:
    from medilab_model_types import Model_res_config_settings as ResConfigSettingsBase
else:
    ResConfigSettingsBase = object


# Cài Đặt
class ResConfigSettings(models.TransientModel, ResConfigSettingsBase):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    @api.model
    def _get_parameter(self, field_name):
        # sudo: only administrators may read system parameters, while features read them for everyone.
        field = self._fields[field_name]
        stored = self.env["ir.config_parameter"].sudo().get_str(value_as(getattr(field, "config_parameter", None), str))
        if stored in (False, None, ""):
            default = field.default
            return default(self) if callable(default) else default
        settings = self.with_context(clean_context(self.env.context)).sudo()
        return settings.default_get([field_name])[field_name]

    if not TYPE_CHECKING:
        # Days a sample test is due before the date promised to the customer, kept for handling incidents.
        safety_margin_days = fields.Integer(
            config_parameter=SAFETY_MARGIN_PARAMETER,
            default=DEFAULT_SAFETY_MARGIN_DAYS,
            help="Days a sample test is due before the date promised to the customer, kept for handling incidents. "
            "Applies to sample tests whose due date is worked out from now on.",
        )
        # Minutes before a planned task starts that its reminder is sent.
        reminder_lead_minutes = fields.Integer(
            string="Reminder lead (minutes)",
            config_parameter=REMINDER_LEAD_PARAMETER,
            default=DEFAULT_REMINDER_LEAD_MINUTES,
        )
        # Days before a sample's retention ends when testers are reminded to dispose of it.
        sample_retention_reminder_days = fields.Integer(
            string="Retention Reminder Days",
            config_parameter=SAMPLE_RETENTION_REMINDER_PARAMETER,
            default=DEFAULT_SAMPLE_RETENTION_REMINDER_DAYS,
            help="Days before a sample's retention ends when testers are reminded to dispose of it.",
        )
        # The role whose people carry dispatches to subcontractors.
        sample_delivery_role_id = fields.Many2one(
            MODEL_ROLE,
            string="Sample Delivery Staff Role",
            config_parameter=SAMPLE_DELIVERY_ROLE_PARAMETER,
            help="Only people holding this role can carry a dispatch to a subcontractor.",
        )
        # Hours before its due date when a sample test becomes urgent and is scheduled before the others.
        urgency_hours = fields.Integer(
            string="Urgency (hours)",
            config_parameter=URGENCY_HOURS_PARAMETER,
            default=DEFAULT_URGENCY_HOURS,
            help="A sample test due within this many hours is urgent: it gets the next free slot on a machine first.",
        )
