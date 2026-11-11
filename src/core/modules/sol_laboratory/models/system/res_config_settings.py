from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.jobs import CLEANUP_RETENTION_FIELDS
from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS
from odoo.addons.sol_laboratory.constants.settings import (
    AUDIT_RETENTION_PARAMETER,
    DEFAULT_LOCK_TIMEOUT_MINUTES,
    DEFAULT_RETENTION_DAYS,
    DEVICE_RETENTION_PARAMETER,
    JOB_RETENTION_PARAMETER,
    LOCK_RETENTION_PARAMETER,
    LOCK_TIMEOUT_PARAMETER,
    NOTIFICATION_RETENTION_PARAMETER,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_res_config_settings as ResConfigSettingsBase
else:
    ResConfigSettingsBase = object


# Cài Đặt
class ResConfigSettings(models.TransientModel, ResConfigSettingsBase):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    if not TYPE_CHECKING:
        # Days audit entries are kept before the cleanup job archives and removes them; 0 keeps them for ever.
        audit_retention_days = fields.Integer(
            config_parameter=AUDIT_RETENTION_PARAMETER,
            help="Days audit entries are kept before the cleanup job writes them to an archive file and removes them. "
            "0 keeps them for ever.",
        )
        # Minutes without activity after which an editing lock is released.
        lock_timeout_minutes = fields.Integer(
            string="Lock Timeout (minutes)",
            config_parameter=LOCK_TIMEOUT_PARAMETER,
            default=DEFAULT_LOCK_TIMEOUT_MINUTES,
            help="Minutes without activity after which a document locked for editing is free again, so a closed browser "
            "does not block it.",
        )

        # Days finished job items and job runs are kept before the cleanup job removes them.
        job_retention_days = fields.Integer(
            string="Job History (days)",
            config_parameter=JOB_RETENTION_PARAMETER,
            default=DEFAULT_RETENTION_DAYS,
            help="Days done and cancelled job items and ended job runs are kept before the cleanup job removes them. "
            "A run that audit entries or archive files name stays as long as they do.",
        )
        # Days released and expired document locks and laboratory file locks are kept before the cleanup job removes them.
        lock_retention_days = fields.Integer(
            string="Lock History (days)",
            config_parameter=LOCK_RETENTION_PARAMETER,
            default=DEFAULT_RETENTION_DAYS,
            help="Days released and expired document locks and laboratory file locks are kept before the cleanup job "
            "removes them.",
        )
        # Days read notifications are kept before the cleanup job removes them with their pushes.
        notification_retention_days = fields.Integer(
            string="Read Notifications (days)",
            config_parameter=NOTIFICATION_RETENTION_PARAMETER,
            default=DEFAULT_RETENTION_DAYS,
            help="Days read notifications are kept before the cleanup job removes them with their pushes.",
        )
        # Days turned-off mobile devices are kept before the cleanup job removes them.
        device_retention_days = fields.Integer(
            string="Turned-off Devices (days)",
            config_parameter=DEVICE_RETENTION_PARAMETER,
            default=DEFAULT_RETENTION_DAYS,
            help="Days mobile devices that were turned off are kept before the cleanup job removes them.",
        )

    @api.constrains("lock_timeout_minutes")
    def _check_lock_timeout(self):
        # A period of 0 would expire every lock at once, so nobody could keep a document while editing it.
        if any(settings.lock_timeout_minutes < 1 for settings in self):
            raise ValidationError(self.env._("The lock timeout must be at least 1 minute."))

    @api.constrains(*CLEANUP_RETENTION_FIELDS)
    def _check_retention(self):
        # A period of 0 would remove the records as soon as they are finished, before anyone could look at them.
        if any(settings[field] < 1 for settings in self for field in CLEANUP_RETENTION_FIELDS):
            raise ValidationError(self.env._("A retention period must be at least 1 day."))

    @api.constrains("audit_retention_days")
    def _check_audit_retention(self):
        # A negative period would archive and remove entries that are still within it.
        if any(settings.audit_retention_days < 0 for settings in self):
            raise ValidationError(
                self.env._("The audit retention period cannot be negative; 0 keeps entries for ever.")
            )
