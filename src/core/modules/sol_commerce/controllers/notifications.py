from odoo import http
from odoo.http import request

from odoo.addons.sol_commerce.constants.models import MODEL_NOTIFICATION_CONTACT
from odoo.addons.sol_commerce.constants.notifications import (
    EVENT_INVOICE_OVERDUE,
    EVENT_INVOICE_SENT,
    EVENT_ORDER_UPDATED,
    EVENT_PAYMENT_RECEIPT,
    EVENT_PAYMENT_REJECTED,
    EVENT_QUOTATION_SENT,
    EVENT_RESULT_RELEASED,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MAIL_MESSAGE,
    MODEL_MAIL_MESSAGE_SUBTYPE,
    MODEL_NOTIFICATION_PREFERENCE,
)
from odoo.addons.sol_laboratory.constants.notifications import CHANNEL_EMAIL, CHANNEL_POPUP

# The event types a customer chooses for, in the order the page lists them.
CUSTOMER_EVENTS = (
    EVENT_ORDER_UPDATED,
    EVENT_QUOTATION_SENT,
    EVENT_INVOICE_SENT,
    EVENT_INVOICE_OVERDUE,
    EVENT_PAYMENT_RECEIPT,
    EVENT_PAYMENT_REJECTED,
    EVENT_RESULT_RELEASED,
)
RECENT_NOTIFICATIONS = 20


class NotificationPortal(http.Controller):
    @http.route("/my/notifications", type="http", auth="user", methods=["GET"], website=True)
    def portal_notifications(self, **kwargs):
        return request.render("sol_commerce.portal_notification_preferences", self._page_values())

    @http.route("/my/notifications", type="http", auth="user", methods=["POST"], website=True)
    def portal_save_notifications(self, **post):
        preferences = request.env[MODEL_NOTIFICATION_PREFERENCE]
        routes = request.env[MODEL_NOTIFICATION_CONTACT]
        business = self._business()
        contacts = self._contacts(business)
        for event in self._events():
            if not event.mandatory:
                for channel in (CHANNEL_EMAIL, CHANNEL_POPUP):
                    preferences.set_own(event, channel, f"{event.code}:{channel}" in post)
            if business.is_company:
                chosen = contacts.filtered(
                    lambda contact, code=event.code: str(contact.id) == post.get(f"contact:{code}")
                )
                routes.set_own(event, chosen[:1])
        return request.redirect("/my/notifications?saved=1")

    def _business(self):
        return request.env.user.partner_id.commercial_partner_id

    def _contacts(self, business):
        return business.child_ids if business.is_company else business.browse()

    def _events(self):
        events = request.env[MODEL_MAIL_MESSAGE_SUBTYPE].sudo().search([("code", "in", CUSTOMER_EVENTS)])
        return events.sorted(key=lambda event: CUSTOMER_EVENTS.index(event.code))

    def _page_values(self):
        user = request.env.user
        messages = request.env[MODEL_MAIL_MESSAGE].sudo()
        business = self._business()
        routes = request.env[MODEL_NOTIFICATION_CONTACT].sudo().search([("partner_id", "=", business.id)])
        rows = []
        for event in self._events():
            popup, email, _push = messages._preferred_channels(user, event)
            rows.append(
                {
                    "event": event,
                    "mandatory": event.mandatory,
                    "email": email or event.mandatory,
                    "popup": popup,
                    "contact_id": routes.filtered(lambda route, event=event: route.event_id == event).contact_id.id,
                }
            )
        inbox = (
            request.env["mail.notification"]
            .sudo()
            .search(
                [("res_partner_id", "in", user.partner_id.ids), ("notification_type", "=", "inbox")],
                order="id desc",
                limit=RECENT_NOTIFICATIONS,
            )
        )
        return {
            "rows": rows,
            "is_business": business.is_company,
            "contacts": self._contacts(business),
            "notifications": inbox.mail_message_id,
            "page_name": "notifications",
        }
