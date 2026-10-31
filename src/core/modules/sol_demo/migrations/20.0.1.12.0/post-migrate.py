from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_laboratory.constants.settings import SAMPLE_DELIVERY_ROLE_PARAMETER


def migrate(cr, _version):
    # The demo sample delivery staff carry dispatches, unless the administrator named another role.
    env = api.Environment(cr, SUPERUSER_ID, {})
    role = env.ref("sol_demo.demo_role_sample_delivery_staff", raise_if_not_found=False)
    parameters = env["ir.config_parameter"]
    if role and not parameters.get_int(SAMPLE_DELIVERY_ROLE_PARAMETER):
        parameters.set_int(SAMPLE_DELIVERY_ROLE_PARAMETER, role.id)
