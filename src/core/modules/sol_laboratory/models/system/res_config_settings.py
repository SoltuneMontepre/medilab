from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS
from odoo.addons.sol_laboratory.constants.settings import AUDIT_RETENTION_PARAMETER


# Cài Đặt
class ResConfigSettings(models.TransientModel):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    # Days audit entries are kept before the cleanup job archives and removes them; 0 keeps them for ever.
    audit_retention_days = fields.Integer(
        config_parameter=AUDIT_RETENTION_PARAMETER,
        help="Days audit entries are kept before the cleanup job writes them to an archive file and removes them. "
        "0 keeps them for ever.",
    )
