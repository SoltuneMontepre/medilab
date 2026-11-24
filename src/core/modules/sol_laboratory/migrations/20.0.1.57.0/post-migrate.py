from odoo import api
from odoo.api import SUPERUSER_ID

PREFIXES = {
    "medilab.sample": "PTN.%(range_y)s.%(range_month)s.",
    "medilab.test.request": "YC.%(range_y)s.%(range_month)s.",
}


def migrate(cr, _version):
    # The sequences are shipped data that is not updated, so their prefixes change here. Their yearly ranges go, as
    # each month gets a range of its own.
    env = api.Environment(cr, SUPERUSER_ID, {})
    for code, prefix in PREFIXES.items():
        sequence = env["ir.sequence"].search([("code", "=", code)])
        sequence.date_range_ids.unlink()
        sequence.prefix = prefix
