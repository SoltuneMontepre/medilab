from datetime import timedelta

from odoo import fields
from odoo.fields import Command

from .demo_orders import _product, _xml_id
from odoo.addons.sol_commerce.constants.models import (
    MODEL_ACCOUNT_MOVE,
    MODEL_ORDER_SAMPLE,
    MODEL_QUOTATION,
    MODEL_SALE_ORDER,
)

DISCOUNT_WIZARD = "sale.order.discount"
PAYMENT_WIZARD = "account.payment.register"


def seed_quotations(env):
    if env.ref("sol_demo.demo_sale_order_quotation_draft", raise_if_not_found=False):
        return
    if not env.company.chart_template:
        # Advance invoices need the sales journal, which a chart of accounts brings; a fresh install has none yet.
        env["account.chart.template"].try_loading("vn", env.company)
    sales = env.ref("sol_demo.demo_res_users_sales")
    head = env.ref("sol_demo.demo_res_users_head_of_sales")
    vat8 = _sales_tax(env, 8)
    vat10 = _sales_tax(env, 10)
    lead = _product(env, "parameter_id", env.ref("sol_demo.demo_parameter_price_lead").parameter_id.id)
    package = _product(env, "service_package_id", env.ref("sol_demo.demo_service_package_bottled_water_basic").id)

    draft = _quotable_order(env, lead, vat10)
    sent = _quotable_order(env, package, vat10, discount=10)
    accepted = _quotable_order(env, lead, vat8, quantity=2, advance_method="bank_transfer", advance_mode="full")
    declined = _quotable_order(env, lead, vat10)
    expired = _quotable_order(env, lead, vat8)
    revised = _quotable_order(env, lead, vat10, quantity=3, advance_method="none")
    for order in (sent, accepted, declined, expired):
        order.with_user(sales).action_send_quotation()
    _pay_advance(env, accepted)
    declined._latest_quotation().action_decline("The price is above our budget this quarter.")
    expired.payment_deadline = fields.Datetime.now() - timedelta(days=1)
    env[MODEL_QUOTATION]._flag_expired()
    revised.with_user(head).action_send_quotation()
    revised.with_user(sales).action_revise_quotation()
    env[DISCOUNT_WIZARD].create(
        {"sale_order_id": revised.id, "discount_type": "so_discount", "discount_percentage": 0.05}
    ).action_apply_discount()
    revised.with_user(head).action_send_quotation()

    requested = _confirmed_order(env, lead, vat10, sales, head)
    approved = _confirmed_order(env, package, vat8, sales, head)
    rejected = _confirmed_order(env, lead, vat8, sales, head)
    requested.with_user(sales).action_request_approval()
    approved.with_user(sales).action_request_approval()
    approved.with_user(head).action_sign()
    rejected.with_user(sales).action_request_approval()
    rejected.with_user(head).action_reject("The discount agreed with the customer is not on the order.")

    for xml_id, record in (
        ("demo_sale_order_quotation_draft", draft),
        ("demo_sale_order_quotation_sent", sent),
        ("demo_sale_order_quotation_accepted", accepted),
        ("demo_sale_order_quotation_declined", declined),
        ("demo_sale_order_quotation_expired", expired),
        ("demo_sale_order_quotation_revised", revised),
        ("demo_sale_order_approval_requested", requested),
        ("demo_sale_order_approval_approved", approved),
        ("demo_sale_order_approval_rejected", rejected),
    ):
        _xml_id(env, xml_id, record)


def _sales_tax(env, rate):
    """The company's sales VAT of the rate; the chart of accounts may not have it, so it is added to a tax group."""
    taxes = env["account.tax"]
    tax = taxes.search([("type_tax_use", "=", "sale"), ("amount_type", "=", "percent"), ("amount", "=", rate)], limit=1)
    if tax:
        return tax
    country = env.company.account_fiscal_country_id or env.ref("base.vn")
    groups = env["account.tax.group"]
    group = groups.search([("country_id", "in", [False, country.id])], limit=1) or groups.create({"name": "VAT"})
    return taxes.create(
        {
            "name": f"VAT {rate}%",
            "amount": rate,
            "amount_type": "percent",
            "type_tax_use": "sale",
            "country_id": country.id,
            "tax_group_id": group.id,
        }
    )


def _quotable_order(
    env, product, tax, quantity=1, discount=0.0, advance_method="online", advance_mode="percentage", advance_value=30
):
    """A claimed order of the salesperson whose items are all tested on one bottled water sample."""
    order = env[MODEL_SALE_ORDER].create(
        {
            "partner_id": env.ref("sol_demo.demo_partner_hoa").id,
            "customer_id": env.ref("sol_demo.demo_partner_nuoc_sach").id,
            "source": "portal",
            "order_status": "claimed",
            "user_id": env.ref("sol_demo.demo_res_users_sales").id,
            "advance_method": advance_method,
            "advance_mode": advance_mode,
            "advance_value": advance_value,
            "order_line": [Command.create({"product_id": product.product_variant_ids.id, "product_uom_qty": quantity})],
        }
    )
    line = order._catalog_lines()
    line.write({"tax_ids": [Command.set(tax.ids)], "discount": discount})
    line.sample_id = env[MODEL_ORDER_SAMPLE].create(
        {
            "order_id": order.id,
            "customer_sample_name": "Nước uống đóng chai 500 ml",
            "sample_type_id": env.ref("sol_demo.sample_type_bottled_water").id,
            "physical_state": "liquid",
        }
    )
    return order


def _confirmed_order(env, product, tax, sales, head):
    """An order the Head of Sales quoted without an advance, the customer accepted and sales confirmed."""
    order = _quotable_order(env, product, tax, advance_method="none")
    order.with_user(head).action_send_quotation()
    order._latest_quotation().action_accept()
    order.with_user(sales).action_confirm_order()
    return order


def _pay_advance(env, order):
    invoices = order.sudo().invoice_ids
    env[PAYMENT_WIZARD].with_context(active_model=MODEL_ACCOUNT_MOVE, active_ids=invoices.ids).create(
        {}
    ).action_create_payments()
