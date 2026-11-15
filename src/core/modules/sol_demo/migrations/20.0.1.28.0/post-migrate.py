from odoo import SUPERUSER_ID, api

from odoo.addons.sol_demo.demo_payment_requests import seed_payment_requests


def migrate(cr, _version):
    seed_payment_requests(api.Environment(cr, SUPERUSER_ID, {}))
