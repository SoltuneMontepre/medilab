from odoo import fields
from odoo.fields import Command

from odoo.addons.sol_commerce.constants.models import MODEL_PRODUCT_TEMPLATE, MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.xml_ids import ALL_ORDERS_GROUP


def seed_orders(env):
    if env.ref("sol_demo.demo_sale_order_draft", raise_if_not_found=False):
        return
    env.ref("sol_demo.demo_res_users_head_of_sales").write({"group_ids": [Command.link(env.ref(ALL_ORDERS_GROUP).id)]})
    company = env.ref("sol_demo.demo_res_partner_nuoc_sach")
    hoa = env.ref("sol_demo.demo_res_partner_hoa")
    minh = env.ref("sol_demo.demo_res_partner_minh")
    sales = env.ref("sol_demo.demo_res_users_sales")
    customer = env.ref("sol_demo.demo_res_users_customer")
    lead = _product(env, "parameter_id", env.ref("sol_demo.demo_parameter_price_lead").parameter_id.id)
    package = _product(env, "service_package_id", env.ref("sol_demo.demo_service_package_bottled_water_basic").id)
    orders = env[MODEL_SALE_ORDER]

    draft = _order(orders, hoa, company, "draft", lead, quantity=2)
    submitted = _order(orders, hoa, company, "submitted", package, submitted_at="2026-03-01 08:00:00")
    claimed = _order(orders, hoa, company, "claimed", lead, user_id=sales.id, claimed_at=fields.Datetime.now())
    confirmed = _order(
        orders,
        hoa,
        company,
        "confirmed",
        lead,
        user_id=sales.id,
        expected_result_date="2026-04-15",
    )
    declined_order = _order(orders, hoa, company, "confirmed", package, user_id=sales.id)
    accepted_order = _order(orders, hoa, company, "confirmed", lead, user_id=sales.id)
    completed = _order(orders, hoa, company, "completed", lead, quantity=2, user_id=sales.id)
    behalf = (
        orders.with_user(sales)
        .with_context(medilab_sales_order=True)
        .create(
            {
                "partner_id": minh.id,
                "customer_id": minh.id,
                "order_line": [_line(lead, 1)],
            }
        )
    )
    reorder = completed.sudo().action_reorder()
    open_request = confirmed.with_user(customer).action_request_cancellation(
        "We sent the wrong sample and need to stop this order."
    )
    declined = declined_order.with_user(customer).action_request_cancellation("The production lot was cancelled.")
    declined.with_user(sales).write({"reply": "The samples are already in testing, so the order continues."})
    declined.with_user(sales).action_decline()
    accepted = accepted_order.with_user(customer).action_request_cancellation("The customer no longer needs the tests.")
    accepted.with_user(sales).action_accept()

    for xml_id, record in (
        ("demo_sale_order_draft", draft),
        ("demo_sale_order_submitted", submitted),
        ("demo_sale_order_claimed", claimed),
        ("demo_sale_order_confirmed", confirmed),
        ("demo_sale_order_declined", declined_order),
        ("demo_sale_order_completed", completed),
        ("demo_sale_order_sales", behalf),
        ("demo_sale_order_reorder", reorder),
        ("demo_cancellation_request_open", open_request),
        ("demo_cancellation_request_declined", declined),
        ("demo_cancellation_request_accepted", accepted),
    ):
        _xml_id(env, xml_id, record)


def _product(env, field_name, owner_id):
    return env[MODEL_PRODUCT_TEMPLATE].search([(field_name, "=", owner_id)], limit=1)


def _line(product, quantity):
    return Command.create({"product_id": product.product_variant_ids.id, "product_uom_qty": quantity})


def _order(orders, contact, customer, status, product, quantity=1, **extra):
    return orders.create(
        {
            "partner_id": contact.id,
            "customer_id": customer.id,
            "source": "portal",
            "order_status": status,
            "user_id": False,
            "order_line": [_line(product, quantity)],
            **extra,
        }
    )


def _xml_id(env, name, record):
    env["ir.model.data"]._update_xmlids([{"xml_id": f"sol_demo.{name}", "record": record, "noupdate": True}])
