from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_ENTRY,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_laboratory.constants.notifications import EVENT_TASK_REMINDER, VIETNAM_ZONE
from odoo.addons.sol_laboratory.constants.settings import DEFAULT_REMINDER_LEAD_MINUTES
from odoo.addons.sol_laboratory.models.system.scheduled_job import PermanentJobError
from odoo.addons.sol_laboratory.services.firebase_client import (
    PermanentTokenError,
    TemporaryFirebaseError,
    firebase_client_from_env,
)

VIETNAM = ZoneInfo(VIETNAM_ZONE)


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model):
    _inherit = MODEL_SCHEDULED_JOB

    def _run_batch(self):
        if self.key == "notifications.remind":
            self._queue_task_reminders()
        return super()._run_batch()

    def _queue_task_reminders(self):
        lead = self._reminder_lead()
        now = datetime.now(VIETNAM)
        start = now.astimezone(UTC).replace(tzinfo=None)
        end = (now + timedelta(minutes=lead)).astimezone(UTC).replace(tzinfo=None)
        # A run that starts a few minutes late still sends the reminder once. The item key stops a second one.
        grace = start - timedelta(minutes=5)
        events = (
            self.env["calendar.event"]
            .sudo()
            .search(
                [
                    "|",
                    ("medilab_task_id", "!=", False),
                    ("medilab_booking_ids", "!=", False),
                    ("start", ">", grace),
                    ("start", "<=", end),
                ]
            )
        )
        for event in events:
            stamp = fields.Datetime.to_string(event.start)
            self.env[MODEL_SCHEDULED_JOB].queue("notifications.remind", f"{event.id}:{stamp}", document=event)

    def _handle_notifications_remind(self, item):
        event = item._document()
        if not event or not event.exists() or not event.start:
            return
        task = event.medilab_task_id or event.medilab_booking_ids.task_id[:1]
        if not task:
            return
        stamp = fields.Datetime.to_string(event.start)
        if item.item_key != f"{event.id}:{stamp}":
            return
        partner = event.user_id.partner_id
        if not partner:
            return
        self.env["mail.message"].raise_event(
            EVENT_TASK_REMINDER,
            task,
            f"calendar:{event.id}:reminder:{stamp}",
            self.env._("Starts at %(start)s.", start=stamp),
            subject=task.name,
            partners=partner,
        )

    def _handle_notifications_email(self, item):
        mail = item._document()
        if not mail or not mail.exists() or mail.state == "sent":
            return
        if mail.state == "cancel":
            raise PermanentJobError(self.env._("The email was cancelled."))
        if mail.state == "exception" and mail.failure_type not in (False, "mail_smtp", "unknown"):
            raise PermanentJobError(mail.failure_reason or self.env._("The email cannot be sent."))
        mail.sudo().write({"state": "outgoing", "failure_reason": False, "failure_type": False})
        mail.sudo().send(raise_exception=False)
        mail.invalidate_recordset()
        if mail.state == "exception":
            raise UserError(mail.failure_reason or self.env._("The mail server did not accept the message."))

    def _handle_notifications_push(self, item):
        delivery = item._document()
        if not delivery or not delivery.exists() or delivery.status in ("sent", "skipped"):
            return None
        device = delivery.mobile_device_id
        if not device.active:
            delivery.write({"status": "skipped"})
            return None
        client = firebase_client_from_env()
        if client is None:
            return fields.Datetime.now() + timedelta(minutes=5)
        message = delivery.notification_id.mail_message_id
        try:
            client.send(device.token, message.subject or "", self._push_body(delivery))
        except PermanentTokenError as error:
            device._audit("error", self.env._("Firebase rejected the token: %s", error))
            device.turn_off(str(error))
            delivery.write({"status": "skipped", "error": str(error)})
            return None
        except TemporaryFirebaseError as error:
            delivery.write({"status": "pending", "error": str(error)})
            raise
        delivery.write({"status": "sent", "sent_at": fields.Datetime.now(), "error": False})
        self.env[MODEL_AUDIT_ENTRY]._log_event(
            "integration",
            self.env._("Push sent to %(user)s on %(platform)s", user=device.user_id.name, platform=device.platform),
            message._audit_document(),
        )
        return None

    def _push_body(self, delivery):
        message = delivery.notification_id.mail_message_id
        return message.preview or message.subject or message.body or ""

    @api.model
    def _reminder_lead(self):
        settings = self.env[MODEL_RES_CONFIG_SETTINGS]
        stored = (
            settings._get_parameter("reminder_lead_minutes") if "reminder_lead_minutes" in settings._fields else None
        )
        return stored or DEFAULT_REMINDER_LEAD_MINUTES
