from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_commerce.constants.xml_ids import SALE_PORTAL_ENTRIES
from odoo.addons.sol_laboratory.services.model_lookup import reference_as

MODEL_PORTAL_ENTRY = "portal.entry"


# Sale keeps its portal cards as noupdate records, so the module data hides them only on a new install.
def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xml_id in SALE_PORTAL_ENTRIES:
        entry = reference_as(env[MODEL_PORTAL_ENTRY], xml_id, raise_if_not_found=False)
        if entry:
            entry.show_in_portal = False
