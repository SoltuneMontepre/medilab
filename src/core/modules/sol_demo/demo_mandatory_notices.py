from .demo_orders import _xml_id
from odoo.addons.sol_commerce.constants.notifications import EVENT_INVOICE_SENT, EVENT_PAYMENT_RECEIPT
from odoo.addons.sol_laboratory.constants.models import MODEL_MAIL_MESSAGE

# The notices in demo.registered's portal, by the end of their xml id: the event, the subject, the text and whether the
# customer already opened it.
NOTICES = (
    ("invoice_sent", EVENT_INVOICE_SENT, "Invoice HD-0001", "Invoice HD-0001 is ready in your portal.", False),
    ("payment_receipt", EVENT_PAYMENT_RECEIPT, "Payment receipt", "We received your payment of 1,000,000 VND.", True),
)


def seed_mandatory_notices(env):
    """demo.registered's portal: mandatory notices whose email never left because the address bounced, one not yet
    opened and one already opened. Posted as the notice job posts them."""
    tai = env.ref("sol_demo.demo_res_partner_tai")
    business = env.ref("sol_demo.demo_customer_nong_san_registered")
    tai.sudo().email_bounced = True
    for name, code, subject, body, opened in NOTICES:
        message = env[MODEL_MAIL_MESSAGE].raise_event(
            code, business, f"demo:{name}", body, subject=subject, partners=tai
        )
        notification = message.notification_ids.filtered(lambda item: item.res_partner_id == tai)
        if opened and not notification.portal_seen_at:
            notification._portal_open()
        _xml_id(env, f"demo_mail_message_{name}", message)
