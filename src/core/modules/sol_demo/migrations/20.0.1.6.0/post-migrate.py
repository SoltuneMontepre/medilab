from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.fields import Command

from odoo.addons.sol_laboratory.services.record_id import persisted_id


def migrate(cr, _version):
    # The accountant confirms and rejects payments, which needs Odoo's billing group.
    env = api.Environment(cr, SUPERUSER_ID, {})
    accountant = env.ref("sol_demo.demo_res_users_accountant", raise_if_not_found=False)
    if accountant:
        accountant.write({"group_ids": [Command.link(persisted_id(env.ref("account.group_account_invoice")))]})
