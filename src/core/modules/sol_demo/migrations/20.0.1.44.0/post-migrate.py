from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.fields import Command

from odoo.addons.sol_laboratory.constants.models import MODEL_ROLE
from odoo.addons.sol_laboratory.services.model_lookup import reference_as
from odoo.addons.sol_laboratory.services.record_id import persisted_id

ROLE_PERMISSIONS = {
    "sol_demo.demo_role_head_of_department": (
        "sol_laboratory.permission_plan_revision_read_own_department",
        "sol_laboratory.permission_plan_revision_move_read_own_department",
    ),
    "sol_demo.demo_role_sales": (
        "sol_laboratory.permission_plan_revision_read_all",
        "sol_laboratory.permission_plan_revision_move_read_all",
    ),
    "sol_demo.demo_role_sample_delivery_staff": ("sol_laboratory.permission_test_report_deliver_all",),
}


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for role_xml_id, permission_xml_ids in ROLE_PERMISSIONS.items():
        role = reference_as(env[MODEL_ROLE], role_xml_id, raise_if_not_found=False)
        if role:
            role.permission_ids = [Command.link(persisted_id(env.ref(xml_id))) for xml_id in permission_xml_ids]
