import os

from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.fields import Command

from odoo.addons.sol_demo.hooks import DEFAULT_DEMO_PASSWORD, DEMO_PASSWORD_VARIABLE
from odoo.addons.sol_laboratory.services.record_id import persisted_id


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # The Microbiology tester signs in, so Microbiology records receiving the samples handed to it.
    user = env.ref("sol_demo.demo_res_users_microbiology_tester", raise_if_not_found=False)
    person = env.ref("sol_demo.demo_person_microbiology_tester", raise_if_not_found=False)
    if user and person:
        user.password = os.environ.get(DEMO_PASSWORD_VARIABLE) or DEFAULT_DEMO_PASSWORD
        person.user_id = user
    # Sample delivery staff choose the person who took the samples on a handover record.
    role = env.ref("sol_demo.demo_role_sample_delivery_staff", raise_if_not_found=False)
    if role:
        role.permission_ids = [
            Command.link(persisted_id(env.ref("sol_laboratory.permission_person_read_own_department")))
        ]
