from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_datetime

from odoo.addons.sol_laboratory.constants.jobs import JOB_RUN_CONTEXT
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_ENTRY,
    MODEL_JOB_RUN,
    MODEL_MAIL_NOTIFICATION,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_laboratory.constants.notifications import (
    EVENT_LOCATION_BOOKING_REMINDER,
    EVENT_TASK_REMINDER,
    PUSH_JOB,
    PUSH_PASS_SECONDS,
    VIETNAM_ZONE,
)
from odoo.addons.sol_laboratory.constants.settings import DEFAULT_REMINDER_LEAD_MINUTES
from odoo.addons.sol_laboratory.models.system.scheduled_job import CRON_PASS_KEY, PermanentJobError
from odoo.addons.sol_laboratory.services.firebase_client import (
    PermanentTokenError,
    TemporaryFirebaseError,
    firebase_client_from_env,
)
from odoo.addons.sol_laboratory.services.staff_language import staff_env

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_scheduled_job as ScheduledJobBase
else:
    ScheduledJobBase = object

VIETNAM = ZoneInfo(VIETNAM_ZONE)
# The Firebase client of the latest run of the push job, by the run's id; a new run finds the credentials again.
_RUN_CLIENT = {}


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model, ScheduledJobBase):
    _inherit = MODEL_SCHEDULED_JOB

    def _run_batch(self):
        if self.key == "notifications.remind":
            self._queue_task_reminders()
        # A pass of the push cron that spent its time ends, and Odoo starts the next one once the other crons had
        # their turn: the cron worker is shared by every job.
        if self.key == PUSH_JOB and self._push_pass_spent():
            self._progress(remaining=self._due_count(fields.Datetime.now()))
            return self.env[MODEL_JOB_RUN]
        return super()._run_batch()

    def _push_pass_spent(self):
        """Whether this pass of the push cron ran longer than PUSH_PASS_SECONDS. Runs outside the cron are not timed."""
        if not self._in_cron():
            return False
        run = self.env[MODEL_JOB_RUN].browse(self.env.context.get(JOB_RUN_CONTEXT) or []).sudo()
        if not run.exists():
            cron_pass = str(self.env.context.get(CRON_PASS_KEY))
            run = run.search([("job_id", "=", self.id), ("cron_pass", "=", cron_pass)], limit=1)
        if not run.started_at:
            return False
        return (fields.Datetime.now() - run.started_at).total_seconds() > PUSH_PASS_SECONDS

    def _push_client(self):
        """The Firebase client of this run of the push job: finding credentials off Google Cloud takes seconds, so a
        run finds them once, not for each push."""
        run_id = self.env.context.get(JOB_RUN_CONTEXT)
        if not run_id:
            return firebase_client_from_env()
        if run_id not in _RUN_CLIENT:
            _RUN_CLIENT.clear()
            _RUN_CLIENT[run_id] = firebase_client_from_env()
        return _RUN_CLIENT[run_id]

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
                    "|",
                    ("medilab_task_id", "!=", False),
                    ("medilab_booking_ids", "!=", False),
                    ("location_id", "!=", False),
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
        stamp = fields.Datetime.to_string(event.start)
        if item.item_key != f"{event.id}:{stamp}":
            return
        task = event.medilab_task_id or event.medilab_booking_ids.task_id[:1]
        if not task:
            if event.location_id and event.active:
                env = self._reminder_env(event.user_id)
                self.env["mail.message"].raise_event(
                    EVENT_LOCATION_BOOKING_REMINDER,
                    event,
                    f"calendar:{event.id}:reminder:{stamp}",
                    env._(
                        "Starts at %(start)s in %(location)s.",
                        start=format_datetime(env, event.start, tz=env.context["tz"]),
                        location=event.location,
                    ),
                    subject=event.name,
                    partners=event.partner_ids,
                )
            return
        partner = event.user_id.partner_id
        if not partner:
            return
        env = self._reminder_env(event.user_id)
        self.env["mail.message"].raise_event(
            EVENT_TASK_REMINDER,
            task,
            f"calendar:{event.id}:reminder:{stamp}",
            env._("Starts at %(start)s.", start=format_datetime(env, event.start, tz=env.context["tz"])),
            subject=task.name,
            partners=partner,
        )

    def _reminder_env(self, user):
        """The environment that writes a reminder in the language and time zone of the person it reminds."""
        tz = (user and user.tz) or self.env.company.partner_id.tz or VIETNAM_ZONE
        env = staff_env(self.env, user)
        return env(context=dict(env.context, tz=tz))

    def _handle_notifications_email(self, item):
        mail = item._document()
        if not mail or not mail.exists() or mail.state == "sent":
            return None
        notification = self.env[MODEL_MAIL_NOTIFICATION].sudo().search(
            [
                ("mail_mail_id", "=", mail.id),
                ("mail_message_id.subtype_id.mandatory", "=", True),
            ],
            limit=1,
        )
        if notification and notification.res_partner_id.email_bounced:
            mail.sudo().write({"state": "cancel"})
            notification.sudo().write({"notification_status": "bounce", "failure_type": "mail_bounce"})
            return None
        if mail.state == "cancel":
            raise PermanentJobError(self.env._("The email was cancelled."))
        if mail.state == "exception" and mail.failure_type not in (False, "mail_smtp", "unknown"):
            if notification:
                notification._mark_email_bounced(notification.email_retry_attempts + 1)
                return None
            raise PermanentJobError(mail.failure_reason or self.env._("The email cannot be sent."))
        mail.sudo().write({"state": "outgoing", "failure_reason": False, "failure_type": False})
        mail.sudo().send(raise_exception=False)
        mail.invalidate_recordset()
        if mail.state == "exception":
            if notification:
                return notification._schedule_email_retry()
            raise UserError(mail.failure_reason or self.env._("The mail server did not accept the message."))
        return None

    def _handle_notifications_push(self, item):
        delivery = item._document()
        if not delivery or not delivery.exists() or delivery.status in ("sent", "skipped"):
            return None
        device = delivery.mobile_device_id
        if not device._signed_in():
            delivery.write({"status": "skipped"})
            return None
        if self._push_pass_spent():
            return fields.Datetime.now()
        client = self._push_client()
        if client is None:
            return fields.Datetime.now() + timedelta(minutes=5)
        message = delivery._message()
        try:
            client.send(device.token, *delivery._push_message())
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

    @api.model
    def _reminder_lead(self):
        settings = self.env[MODEL_RES_CONFIG_SETTINGS]
        stored = (
            settings._get_parameter("reminder_lead_minutes") if "reminder_lead_minutes" in settings._fields else None
        )
        return stored or DEFAULT_REMINDER_LEAD_MINUTES
