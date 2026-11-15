from odoo import api
from odoo.api import SUPERUSER_ID


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    expiration = env.ref("sol_commerce.cron_flag_expired_quotations", raise_if_not_found=False)
    if expiration and expiration.interval_type == "days" and expiration.interval_number == 1:
        expiration.write({"interval_number": 5, "interval_type": "minutes"})
