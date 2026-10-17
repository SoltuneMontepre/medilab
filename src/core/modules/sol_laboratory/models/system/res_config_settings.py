from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS
from odoo.addons.sol_laboratory.constants.settings import (
    AUDIT_RETENTION_PARAMETER,
    DEFAULT_LOCK_TIMEOUT_MINUTES,
    LOCK_TIMEOUT_PARAMETER,
)


# Cài Đặt
class ResConfigSettings(models.TransientModel):
    _inherit = MODEL_RES_CONFIG_SETTINGS

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

    @api.constrains("lock_timeout_minutes")
    def _check_lock_timeout(self):
        # A period of 0 would expire every lock at once, so nobody could keep a document while editing it.
        if any(settings.lock_timeout_minutes < 1 for settings in self):
            raise ValidationError(self.env._("The lock timeout must be at least 1 minute."))
