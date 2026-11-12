from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.fields import Command

from odoo.addons.sol_laboratory.constants.models import MODEL_ROLE
from odoo.addons.sol_laboratory.services.model_lookup import reference_as
from odoo.addons.sol_laboratory.services.record_id import persisted_id

# The head of department records the OverTime of their department's testers.
PERMISSIONS = (
    "sol_laboratory.permission_overtime_read_own_department",
    "sol_laboratory.permission_overtime_create_own_department",
    "sol_laboratory.permission_overtime_edit_own_department",
    "sol_laboratory.permission_overtime_delete_own_department",
)


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    role = reference_as(env[MODEL_ROLE], "sol_demo.demo_role_head_of_department", raise_if_not_found=False)
    if role:
        role.permission_ids = [Command.link(persisted_id(env.ref(xml_id))) for xml_id in PERMISSIONS]
