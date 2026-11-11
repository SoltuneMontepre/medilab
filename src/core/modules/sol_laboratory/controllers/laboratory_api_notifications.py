from odoo import http

from odoo.addons.sol_laboratory.constants.medilab_mobile import NOTIFICATION_PAGE_SIZE
from odoo.addons.sol_laboratory.constants.models import MODEL_MAIL_NOTIFICATION
from odoo.addons.sol_laboratory.services.laboratory_api import laboratory_api_route


class LaboratoryApiNotifications(http.Controller):
    """The person's inbox notifications on Medilab Mobile, the same as the web's inbox."""

    @laboratory_api_route("/notifications", ["GET"], "listNotifications", permission=False)
    def list_notifications(self, device, _body, after="0", limit=None):
        limit = int(limit or NOTIFICATION_PAGE_SIZE)
        notifications = device.env[MODEL_MAIL_NOTIFICATION]._inbox_after(int(after), limit + 1).with_env(device.env)
        return {
            "notifications": [notification._mobile_values() for notification in notifications[:limit]],
            "next_after": notifications[limit - 1].id if len(notifications) > limit else None,
        }

    @laboratory_api_route("/notifications/<int:message_id>/read", ["POST"], "readNotification", permission=False)
    def read_notification(self, device, _body, message_id):
        device.env[MODEL_MAIL_NOTIFICATION]._mark_inbox_read(message_id)
