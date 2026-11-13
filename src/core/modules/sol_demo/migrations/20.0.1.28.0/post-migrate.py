from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.fields import Command

from odoo.addons.sol_demo.demo_figures import seed_figures
from odoo.addons.sol_laboratory.constants.models import MODEL_ROLE
from odoo.addons.sol_laboratory.services.model_lookup import reference_as
from odoo.addons.sol_laboratory.services.record_id import persisted_id

# The head reads the testing figures of their department; the Lab Head reads those of every department.
PERMISSIONS = (
    ("sol_demo.demo_role_head_of_department", "sol_laboratory.permission_testing_figure_read_own_department"),
    ("sol_demo.demo_role_lab_head", "sol_laboratory.permission_testing_figure_read_all"),
)


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for role_xml_id, permission_xml_id in PERMISSIONS:
        role = reference_as(env[MODEL_ROLE], role_xml_id, raise_if_not_found=False)
        if role:
            role.permission_ids = [Command.link(persisted_id(env.ref(permission_xml_id)))]
    seed_figures(env)
