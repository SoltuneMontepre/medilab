import math

from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_laboratory.services.model_lookup import reference_as


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # The template example ordered 1.5 Lead (Pb) tests; a template orders whole tests, so its orders are rounded up like
    # the template the E-commerce upgrade rounded up.
    for name in ("demo_sale_order_template_source", "demo_sale_order_from_template"):
        order = reference_as(env[MODEL_SALE_ORDER], f"sol_demo.{name}", raise_if_not_found=False)
        if order and order.state == "draft":
            for line in order._catalog_lines().filtered(lambda line: not float(line.product_uom_qty).is_integer()):
                line.product_uom_qty = math.ceil(line.product_uom_qty)
