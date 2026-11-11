from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ATTACHMENT


def migrate(cr, _version):
    # Files written while the bucket was mounted as the filestore sit at its root, where attachments no longer look.
    env = api.Environment(cr, SUPERUSER_ID, {})
    env[MODEL_IR_ATTACHMENT]._move_mounted_files()
