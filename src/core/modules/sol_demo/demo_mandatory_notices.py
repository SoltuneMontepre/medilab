from datetime import timedelta

from odoo import fields

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
    """Demo portals: a notice awaiting retry, a corrected address awaiting confirmation and notices whose address
    bounced, one not yet opened and one already opened. Posted as the notice job posts them."""
    tai = env.ref("sol_demo.demo_res_partner_tai")
    business = env.ref("sol_demo.demo_customer_nong_san_registered")
    hoa = env.ref("sol_demo.demo_res_partner_hoa")
    hoa_business = env.ref("sol_demo.demo_customer_nuoc_sach")
    message = env[MODEL_MAIL_MESSAGE].sudo().search([("notification_key", "=", "demo:temporary_failure")], limit=1)
    if not message:
        message = env[MODEL_MAIL_MESSAGE].raise_event(
            EVENT_INVOICE_SENT,
            hoa_business,
            "demo:temporary_failure",
            "The invoice email is waiting for a retry after a temporary failure.",
            subject="Invoice email awaiting retry",
            partners=hoa,
        )
        notification = message.notification_ids.filtered(lambda item: item.res_partner_id == hoa)
        notification.write({"brevo_status": "deferred", "notification_status": "exception", "email_retry_count": 1})
        notification.mail_mail_id.write(
            {"state": "exception", "failure_type": "mail_smtp", "failure_reason": "Temporary delivery failure"}
        )
        item = env["medilab.job.item"].search([("item_key", "=", f"mail:{notification.mail_mail_id.id}")], limit=1)
        item.write({"next_attempt_at": fields.Datetime.now() + timedelta(hours=1)})
        _xml_id(env, "demo_mail_message_temporary_failure", message)
    confirmation_message = (
        env[MODEL_MAIL_MESSAGE].sudo().search([("notification_key", "=", "demo:email_correction_waiting")], limit=1)
    )
    if not confirmation_message:
        tai.sudo().email_bounced = True
        tai.write({"email": "tai.confirmed@nongsanxanh.example"})
        confirmation_message = env[MODEL_MAIL_MESSAGE].raise_event(
            EVENT_INVOICE_SENT,
            business,
            "demo:email_correction_waiting",
            "Your corrected email address is waiting for confirmation.",
            subject="Email address awaiting confirmation",
            partners=tai,
        )
        _xml_id(env, "demo_mail_message_email_correction_waiting", confirmation_message)
    tai.sudo().email_bounced = True
    for name, code, subject, body, opened in NOTICES:
        message = env[MODEL_MAIL_MESSAGE].raise_event(
            code, business, f"demo:{name}", body, subject=subject, partners=tai
        )
        notification = message.notification_ids.filtered(lambda item: item.res_partner_id == tai)
        if opened and not notification.portal_seen_at:
            notification._portal_open()
        _xml_id(env, f"demo_mail_message_{name}", message)
