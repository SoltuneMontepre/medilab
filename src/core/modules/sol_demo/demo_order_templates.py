from odoo.fields import Command

from .demo_orders import _xml_id
from odoo.addons.sol_commerce.constants.models import (
    MODEL_ORDER_TEMPLATE,
    MODEL_ORDER_TEMPLATE_LINE,
    MODEL_PRODUCT_TEMPLATE,
    MODEL_SALE_ORDER,
)
from odoo.addons.sol_commerce.constants.xml_ids import ALL_ORDERS_GROUP
from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION


def seed_order_templates(env):
    permissions = env[MODEL_PERMISSION].search(
        [("document_model", "in", [MODEL_ORDER_TEMPLATE, MODEL_ORDER_TEMPLATE_LINE])]
    )
    for role_name in ("sales", "head_of_sales"):
        role = env.ref(f"sol_demo.demo_role_{role_name}")
        role.permission_ids |= permissions
    head = env.ref("sol_demo.demo_res_users_head_of_sales")
    head.group_ids |= env.ref(ALL_ORDERS_GROUP)
    sales = env.ref("sol_demo.demo_res_users_sales")
    source = env.ref("sol_demo.demo_sale_order_template_source", raise_if_not_found=False)
    if not source:
        price = env.ref("sol_demo.demo_parameter_price_lead")
        package = env.ref("sol_demo.demo_service_package_bottled_water_basic")
        products = env[MODEL_PRODUCT_TEMPLATE].search(
            ["|", ("parameter_id", "=", price.parameter_id.id), ("service_package_id", "=", package.id)]
        )
        source = (
            env[MODEL_SALE_ORDER]
            .with_user(sales)
            .sudo()
            .with_context(medilab_sales_order=True)
            .create(
                {
                    "partner_id": env.ref("sol_demo.demo_res_partner_hoa").id,
                    "customer_id": env.ref("sol_demo.demo_res_partner_nuoc_sach").id,
                    "order_line": [
                        Command.create(
                            {
                                "product_id": product.product_variant_ids.id,
                                "product_uom_qty": 1.5 if product.parameter_id else 1,
                            }
                        )
                        for product in products
                    ],
                }
            )
        )
        _xml_id(env, "demo_sale_order_template_source", source)
    template = env.ref("sol_demo.demo_order_template_monthly_water", raise_if_not_found=False)
    if not template:
        template = source.with_user(sales).sudo()._save_as_template("Monthly water check")
        _xml_id(env, "demo_order_template_monthly_water", template)
        for line in template.line_ids:
            suffix = "parameter" if line.product_id.parameter_id else "package"
            _xml_id(env, f"demo_order_template_line_monthly_{suffix}", line)
    if not env.ref("sol_demo.demo_sale_order_from_template", raise_if_not_found=False):
        order = template.with_user(sales).sudo()._create_order()
        _xml_id(env, "demo_sale_order_from_template", order)
    if not env.ref("sol_demo.demo_order_template_archived", raise_if_not_found=False):
        archived = source.with_user(sales).sudo()._save_as_template("Previous water check")
        archived.action_archive()
        _xml_id(env, "demo_order_template_archived", archived)
        for line in archived.line_ids:
            suffix = "parameter" if line.product_id.parameter_id else "package"
            _xml_id(env, f"demo_order_template_line_archived_{suffix}", line)
