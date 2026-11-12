from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_inventory.constants.models import MODEL_PRODUCT, MODEL_STOCK_LOT
from odoo.addons.sol_inventory.constants.xml_ids import STOCK_ITEM_CATEGORY
from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS


def migrate(cr, _version):
    # Stock items made before the costing setting join its category, keep the cost of each lot under first in, first
    # out, and list their lots as expiring soon from the expiry warning.
    env = api.Environment(cr, SUPERUSER_ID, {})
    settings = env[MODEL_RES_CONFIG_SETTINGS]
    items = env[MODEL_PRODUCT].with_context(active_test=False).search([("item_kind", "!=", False)])
    items.product_tmpl_id.write({"categ_id": env.ref(STOCK_ITEM_CATEGORY).id})
    items._sync_lot_valuation()
    env[MODEL_STOCK_LOT]._apply_expiry_warning(settings._get_parameter("expiry_warning_days"))
