from datetime import timedelta

from odoo import fields

from .demo_orders import _product, _xml_id
from .demo_quotations import _pay_advance, _quotable_order, _sales_tax
from .demo_reports import _approve_all
from .demo_results import _enter, _receive
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REPORT

# Orders of each salesperson over the last two months: how many days ago they were claimed, how far they got, and the
# days each step they reached took after the one before.
HISTORY = {
    "sales": (
        (55, "approved", (1, 3, 1)),
        (41, "declined", (2,)),
        (27, "approved", (1, 2, 2)),
        (12, "accepted", (3, 2)),
        (4, "sent", (1,)),
    ),
    "sales_2": (
        (52, "approved", (2, 4, 1)),
        (38, "approved", (1, 5, 3)),
        (30, "declined", (4,)),
        (19, "requested", (2, 1)),
        (9, "sent", (2,)),
        (2, "draft", ()),
    ),
}


def seed_tracking(env):
    """Approved orders of Nước Uống Sạch in testing and with released results, and two months of orders of both
    salespeople across the pipeline."""
    if env.ref("sol_demo.demo_sale_order_tracking_testing", raise_if_not_found=False):
        return
    head = env.ref("sol_demo.demo_res_users_head_of_sales")
    sales = env.ref("sol_demo.demo_res_users_sales")
    lead_product = _product(env, "parameter_id", env.ref("sol_demo.demo_test_parameter_lead").id)
    tax = _sales_tax(env, 8)

    testing = _history_order(env, sales, head, lead_product, tax, "approved")
    _receive(env, testing.test_request_id)
    test = testing.test_request_id.sample_ids.test_ids[:1]
    _enter(env, env.ref("sol_demo.demo_res_users_tester"), test, value=0.003, conclusion="pass")
    released = _history_order(env, sales, head, lead_product, tax, "approved")
    _receive(env, released.test_request_id)
    _approve_all(env, released.test_request_id)
    env[MODEL_TEST_REPORT].search([("request_id", "=", released.test_request_id.id)]).with_user(
        env.ref("sol_demo.demo_res_users_lab_head")
    ).action_sign()
    _xml_id(env, "demo_sale_order_tracking_testing", testing)
    _xml_id(env, "demo_sale_order_tracking_released", released)

    for name, orders in HISTORY.items():
        salesperson = env.ref(f"sol_demo.demo_res_users_{name}")
        for number, (days_ago, outcome, steps) in enumerate(orders, start=1):
            order = _history_order(env, salesperson, head, lead_product, tax, outcome)
            _backdate(order, days_ago, steps)
            _xml_id(env, f"demo_sale_order_history_{name}_{number}", order)


def _history_order(env, salesperson, head, product, tax, outcome):
    """An order the salesperson took as far as the outcome: draft, sent, declined, accepted, requested or approved."""
    order = _quotable_order(env, product, tax, salesperson=salesperson)
    if outcome == "draft":
        return order
    order.with_user(salesperson).action_send_quotation()
    if outcome == "declined":
        order._latest_quotation().action_decline("Another laboratory offered a shorter turnaround.")
    if outcome in ("accepted", "requested", "approved"):
        _pay_advance(env, order)
    if outcome in ("requested", "approved"):
        order.with_user(salesperson).action_confirm_order()
        order.with_user(salesperson).action_request_approval()
    if outcome == "approved":
        order.with_user(head).action_sign()
    return order


def _backdate(order, days_ago, steps):
    """Move the claim into the past, and each step the order reached the given days after the step before."""
    moment = fields.Datetime.now() - timedelta(days=days_ago)
    order.write({"claimed_at": moment, "date_order": moment})
    for step, days in zip(("sent_at", "accepted_at", "approved_at"), steps, strict=False):
        moment += timedelta(days=days)
        (order.quotation_ids if step == "sent_at" else order).write({step: moment})
