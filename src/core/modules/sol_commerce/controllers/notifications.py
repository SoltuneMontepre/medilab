from werkzeug.exceptions import NotFound

from odoo import http
from odoo.fields import Domain
from odoo.http import request

from odoo.addons.portal.controllers.portal import pager as portal_pager
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
    MODEL_MAIL_NOTIFICATION,
    MODEL_NOTIFICATION_PREFERENCE,
)
from odoo.addons.sol_laboratory.constants.notifications import CHANNEL_EMAIL, CHANNEL_POPUP
from odoo.addons.sol_laboratory.constants.routes import FRONTEND_PAGE
from odoo.addons.sol_laboratory.services.request_env import request_env

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
NOTIFICATIONS_PATH = "/my/notifications"
NOTIFICATIONS_PER_PAGE = 20


class NotificationPortal(http.Controller):
    @http.route(
        [NOTIFICATIONS_PATH, f"{NOTIFICATIONS_PATH}/page/<int:page>"],
        type="http",
        auth="user",
        methods=["GET"],
        **FRONTEND_PAGE,
    )
    def portal_notifications(self, page=1, **kwargs):
        return request.render("sol_commerce.portal_notification_preferences", self._page_values(page))

    @http.route(
        f"{NOTIFICATIONS_PATH}/<int:notification_id>", type="http", auth="user", methods=["GET"], **FRONTEND_PAGE
    )
    def portal_notification(self, notification_id, **kwargs):
        """Open one of the signed-in user's own notices; its first open is recorded. A notice that is someone else's
        answers like one that does not exist."""
        model = request_env()[MODEL_MAIL_NOTIFICATION].sudo()
        notification = model.search(
            model._portal_domain(request_env().user) & Domain("id", "=", notification_id), limit=1
        )
        if not notification:
            raise NotFound()
        notification._portal_open()
        return request.render(
            "sol_commerce.portal_notification",
            {"notification": notification, "message": notification.mail_message_id, "page_name": "notifications"},
        )

    @http.route("/my/notifications", type="http", auth="user", methods=["POST"], **FRONTEND_PAGE)
    def portal_save_notifications(self, **post):
        preferences = request_env()[MODEL_NOTIFICATION_PREFERENCE]
        routes = request_env()[MODEL_NOTIFICATION_CONTACT]
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
        return request_env().user.partner_id.commercial_partner_id

    def _contacts(self, business):
        return business.child_ids if business.is_company else business.browse()

    def _events(self):
        events = request_env()[MODEL_MAIL_MESSAGE_SUBTYPE].sudo().search([("code", "in", CUSTOMER_EVENTS)])
        return events.sorted(key=lambda event: CUSTOMER_EVENTS.index(event.code))

    def _page_values(self, page=1):
        user = request_env().user
        messages = request_env()[MODEL_MAIL_MESSAGE].sudo()
        business = self._business()
        routes = request_env()[MODEL_NOTIFICATION_CONTACT].sudo().search([("partner_id", "=", business.id)])
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
        notices = request_env()[MODEL_MAIL_NOTIFICATION].sudo()
        domain = notices._portal_domain(user)
        pager = portal_pager(
            url=NOTIFICATIONS_PATH, total=notices.search_count(domain), page=page, step=NOTIFICATIONS_PER_PAGE
        )
        return {
            "rows": rows,
            "is_business": business.is_company,
            "contacts": self._contacts(business),
            "notifications": notices.search(
                domain, order="id desc", limit=NOTIFICATIONS_PER_PAGE, offset=pager["offset"]
            ),
            "pager": pager,
            "page_name": "notifications",
        }
