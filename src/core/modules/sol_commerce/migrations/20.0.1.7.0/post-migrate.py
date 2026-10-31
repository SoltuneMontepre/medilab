from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_commerce.constants.xml_ids import SALE_PORTAL_ENTRIES


# Sale keeps its portal cards as noupdate records, so the module data hides them only on a new install.
def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xml_id in SALE_PORTAL_ENTRIES:
        entry = env.ref(xml_id, raise_if_not_found=False)
        if entry:
            entry.show_in_portal = False
