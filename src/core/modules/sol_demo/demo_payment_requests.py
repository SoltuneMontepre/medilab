from datetime import timedelta

from odoo import fields

from .demo_orders import _product, _xml_id
from .demo_quotations import _as, _quotable_order, _sales_tax
from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_PAYMENT, MODEL_QUOTATION


def seed_payment_requests(env):
    if env.ref("sol_demo.demo_sale_order_payment_request_open", raise_if_not_found=False):
        return
    sales = env.ref("sol_demo.demo_res_users_sales")
    head = env.ref("sol_demo.demo_res_users_head_of_sales")
    credit_customer = env.ref("sol_demo.demo_res_partner_an_phu")
    product = _product(env, "parameter_id", env.ref("sol_demo.demo_parameter_price_lead").parameter_id.id)
    tax = _sales_tax(env, 8)
    payments = env[MODEL_ACCOUNT_PAYMENT]

    def new_order(**values):
        return _quotable_order(env, product, tax, quantity=2, advance_value=50, **values)

    def collect(order, *, amount=None, verify=True):
        request = order.payment_request_id
        payment = payments._create_request_payment(request, amount or request.remaining_amount, "bank_transfer")
        if verify:
            payment.action_post()
        return payment

    cases = {key: new_order() for key in ("open", "partial", "pending", "funded", "expired", "revised", "balance")}
    for order in cases.values():
        _as(order, sales).action_send_quotation()
    collect(cases["partial"], amount=100_000)
    collect(cases["pending"], amount=100_000, verify=False)
    collect(cases["funded"])
    collect(cases["expired"], amount=100_000)
    cases["expired"].payment_deadline = fields.Datetime.now() - timedelta(days=1)
    env[MODEL_QUOTATION]._flag_expired()
    revised = cases["revised"]
    collect(revised)
    _as(revised, sales).action_revise_quotation()
    revised.advance_value = 40
    _as(revised, sales).action_send_quotation()
    balance = cases["balance"]
    collect(balance)
    _as(balance, sales).action_confirm_order()
    collect(balance)

    for name in ("credit", "credit_invoiced"):
        order = new_order(advance_method="none", partner=credit_customer, company=credit_customer)
        _as(order, head).action_send_quotation()
        order._latest_quotation()._accept()
        _as(order, sales).action_confirm_order()
        cases[name] = order
    completed = cases["credit_invoiced"]
    request = completed.test_request_id
    request.sample_ids.test_ids.write({"status": "approved"})
    request.sample_ids.write({"status": "completed"})
    request.status = "completed"
    completed.create_final_invoice().action_post()

    for name, order in cases.items():
        _xml_id(env, f"demo_sale_order_payment_request_{name}", order)
