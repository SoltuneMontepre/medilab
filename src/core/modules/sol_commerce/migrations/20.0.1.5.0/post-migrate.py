from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.fields import Command

from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION
from odoo.addons.sol_laboratory.constants.xml_ids import ADMINISTRATOR_ROLE
from odoo.addons.sol_laboratory.services.record_id import persisted_id

# Read all and edit all used to cover only the salesperson's orders and the unclaimed queue, which the own-orders
# permissions cover now.
MOVED = {"order.read.all": "order.read.own", "order.edit.all": "order.edit.own"}


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    permissions = env[MODEL_PERMISSION]
    administrator = env.ref(ADMINISTRATOR_ROLE)
    for old_code, new_code in MOVED.items():
        old = permissions.search([("code", "=", old_code)])
        new = permissions.search([("code", "=", new_code)])
        commands = [Command.unlink(persisted_id(old)), Command.link(persisted_id(new))]
        for holders in (old.role_ids - administrator, old.person_ids):
            holders.write({"permission_ids": commands})
