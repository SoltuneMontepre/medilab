from datetime import datetime, time, timedelta

from odoo.fields import Command

from .demo_orders import _product, _xml_id
from .demo_quotations import _sales_tax
from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_MOVE, MODEL_ACCOUNT_PAYMENT
from odoo.addons.sol_commerce.models.invoicing.account_move import VIETNAM

# Invoices of the last three months per customer: name, days ago it was sent, days from then to its due date, days from
# then to its confirmed payment, and the share of the total paid.
INVOICES = {
    "an_phu": (
        ("on_time", 85, 15, 10, 1),
        ("late", 60, 15, 25, 1),
        ("partly_paid", 35, 15, 5, 0.5),
        ("unpaid", 10, 30, 0, 0),
    ),
    "green_farm": (
        ("on_time", 70, 15, 14, 1),
        ("overdue", 80, 15, 0, 0),
        ("late", 20, 15, 18, 1),
    ),
}


def seed_finance(env):
    """Invoices of An Phú and Nông Sản Xanh paid on time, late and in part, unpaid and overdue, one with a package
    line, and a transfer sales recorded that the accountant has not confirmed."""
    if env.ref("sol_demo.demo_account_move_finance_an_phu_on_time", raise_if_not_found=False):
        return
    lead = _product(env, "parameter_id", env.ref("sol_demo.demo_test_parameter_lead").id).product_variant_id
    package = _product(
        env, "service_package_id", env.ref("sol_demo.demo_service_package_bottled_water_basic").id
    ).product_variant_id
    tax = _sales_tax(env, 8)
    today = datetime.now(VIETNAM).date()
    for customer, invoices in INVOICES.items():
        partner = env.ref(f"sol_demo.demo_res_partner_{customer}")
        for name, days_ago, due_in, paid_after, share in invoices:
            sent = today - timedelta(days=days_ago)
            lines = [(package, 1), (lead, 2)] if name == "on_time" else [(lead, 1)]
            invoice = _invoice(env, partner, lines, tax, sent, due_in)
            if share:
                amount = invoice.currency_id.round(invoice.amount_total * share)
                payment = env[MODEL_ACCOUNT_PAYMENT].create_pending_payment(invoice, amount, "bank_transfer")
                payment.date = sent + timedelta(days=paid_after)
                payment.action_post()
            _xml_id(env, f"demo_account_move_finance_{customer}_{name}", invoice)
    unpaid = env.ref("sol_demo.demo_account_move_finance_an_phu_unpaid")
    sales = env.ref("sol_demo.demo_res_users_sales")
    pending = env[MODEL_ACCOUNT_PAYMENT].with_user(sales).sudo().create_pending_payment(unpaid, False, "bank_transfer")
    _xml_id(env, "demo_account_payment_finance_pending", pending)


def _invoice(env, partner, lines, tax, sent, due_in):
    invoice = env[MODEL_ACCOUNT_MOVE].create(
        {
            "move_type": "out_invoice",
            "invoice_kind": "final",
            "partner_id": partner.id,
            "invoice_date": sent,
            "invoice_line_ids": [
                Command.create({"product_id": product.id, "quantity": quantity, "tax_ids": [Command.set(tax.ids)]})
                for product, quantity in lines
            ],
        }
    )
    invoice.invoice_date_due = sent + timedelta(days=due_in)
    invoice.action_post()
    invoice.write({"is_move_sent": True, "sent_at": datetime.combine(sent, time(2))})
    return invoice
