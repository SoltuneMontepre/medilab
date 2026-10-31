from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.fields import Command

from odoo.addons.sol_laboratory.constants.models import MODEL_ROLE
from odoo.addons.sol_laboratory.services.model_lookup import reference_as
from odoo.addons.sol_laboratory.services.record_id import persisted_id

# Sales reads every order and edits its own; the Head of Sales reads and edits every order.
ROLE_PERMISSIONS = {
    "sol_demo.demo_role_sales": ("sol_commerce.permission_order_read_all", "sol_commerce.permission_order_edit_own"),
    "sol_demo.demo_role_head_of_sales": (
        "sol_commerce.permission_order_read_all",
        "sol_commerce.permission_order_edit_all",
    ),
}


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for role_xml_id, permission_xml_ids in ROLE_PERMISSIONS.items():
        role = reference_as(env[MODEL_ROLE], role_xml_id, raise_if_not_found=False)
        if role:
            role.permission_ids = [Command.link(persisted_id(env.ref(xml_id))) for xml_id in permission_xml_ids]
