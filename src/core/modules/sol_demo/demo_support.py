from .demo_orders import _xml_id
from odoo.addons.sol_commerce.constants.models import MODEL_SUPPORT_REQUEST


def seed_support(env):
    if env.ref("sol_demo.demo_support_request_open", raise_if_not_found=False):
        return
    customer = env.ref("sol_demo.demo_res_users_customer")
    sales = env.ref("sol_demo.demo_res_users_sales")
    requests = env[MODEL_SUPPORT_REQUEST].with_user(customer)
    confirmed = env.ref("sol_demo.demo_sale_order_confirmed")
    claimed = env.ref("sol_demo.demo_sale_order_claimed")

    opened = requests.portal_open(
        "When will the results be ready?",
        confirmed.id,
        "We need the lead results before 15 April for our quality audit.",
    )
    answered = requests.portal_open(
        "Sample name on the quotation",
        claimed.id,
        "Please name the sample Lavie 500 mL on the quotation, as on our label.",
    )
    _reply(answered, sales, "Done, the quotation now names the sample Lavie 500 mL.")
    closed = requests.portal_open(
        "Company address on the invoice",
        None,
        "Our invoices must show the company address, not the contact's address.",
    )
    closed.with_user(sales).action_take()
    _reply(closed, sales, "The address is corrected on the invoice and a new copy is on its way.")
    _reply(closed, customer, "Received, thank you.")
    closed.with_user(sales).action_close()
    untaken = requests.portal_open(
        "Export certificate",
        None,
        "Can the laboratory issue an export certificate for our bottled water?",
    )
    env.ref("sol_demo.demo_sale_order_completed").with_user(customer).action_give_feedback(
        5, "Fast results and a clear report."
    )

    for xml_id, record in (
        ("demo_support_request_open", opened),
        ("demo_support_request_answered", answered),
        ("demo_support_request_closed", closed),
        ("demo_support_request_untaken", untaken),
    ):
        _xml_id(env, xml_id, record)


def _reply(request, user, body):
    request.with_user(user).message_post(body=body, message_type="comment", subtype_xmlid="mail.mt_comment")
