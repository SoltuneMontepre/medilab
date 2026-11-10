from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_laboratory.constants.models import MODEL_NOTIFICATION_PREFERENCE
from odoo.addons.sol_laboratory.constants.notifications import CHANNEL_PUSH


def migrate(cr, _version):
    # A mandatory event's push can no longer be turned off; one turned off before is on again, as pushes now treat it.
    env = api.Environment(cr, SUPERUSER_ID, {})
    env[MODEL_NOTIFICATION_PREFERENCE].search(
        [("channel", "=", CHANNEL_PUSH), ("enabled", "=", False), ("event_id.mandatory", "=", True)]
    ).write({"enabled": True})
