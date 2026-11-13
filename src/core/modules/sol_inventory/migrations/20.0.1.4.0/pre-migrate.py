from odoo import api
from odoo.api import SUPERUSER_ID

# Views 20.0.1.3.0 added to forms this version keeps. They name fields this version no longer has, and Odoo checks
# each form it loads together with every view added to it, but deletes these only once every module is updated.
LEFTOVER_VIEWS = (
    "sol_inventory.res_config_settings_view_form_costing",
    "sol_inventory.res_config_settings_view_form_expiry",
    "sol_inventory.view_medilab_test_result_form_containers",
)


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in LEFTOVER_VIEWS:
        view = env.ref(xmlid, raise_if_not_found=False)
        if view:
            # As Odoo deletes leftover records, so views added to these go with them.
            view.with_context(force_delete=True).unlink()
