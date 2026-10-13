import os
from datetime import timedelta
from unittest.mock import patch

import requests

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.sol_laboratory.constants.notifications import (
    BREVO_WEBHOOK_TOKEN,
    CHANNEL_EMAIL,
    EVENT_TASK_REMINDER,
    FIREBASE_CREDENTIALS,
    FIREBASE_PROJECT_ID,
)
from odoo.addons.sol_laboratory.models.system.scheduled_job import PermanentJobError
from odoo.addons.sol_laboratory.services import firebase_client
from odoo.addons.sol_laboratory.services.firebase_client import (
    FirebaseClient,
    PermanentTokenError,
    TemporaryFirebaseError,
)


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _JsonError(_Response):
    def json(self):
        raise ValueError("not json")


class _Credentials:
    def __init__(self, valid=True):
        self.valid = valid
        self.token = "access-token"
        self.refreshed = False

    def refresh(self, request):
        self.refreshed = True
        self.valid = True


@tagged("post_install", "-at_install")
class TestNotifications(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create(
            {
                "name": "Notifier",
                "login": "notifier",
                "email": "notifier@example.com",
                "notification_type": "inbox",
                "group_ids": [(6, 0, cls.env.ref("base.group_user").ids)],
            }
        )
        cls.user.partner_id.email = "notifier@example.com"
        cls.event = cls.env["mail.message.subtype"]._event(EVENT_TASK_REMINDER)
        cls.task_type = cls.env["medilab.task.type"].search([], limit=1)

    def test_the_same_key_returns_one_message(self):
        task = self._task()
        first = self.env["mail.message"].raise_event(
            EVENT_TASK_REMINDER, task, "once", "Body", partners=self.user.partner_id
        )
        second = self.env["mail.message"].raise_event(
            EVENT_TASK_REMINDER, task, "once", "Body", partners=self.user.partner_id
        )
        self.assertEqual(first, second)
        mine = first.notification_ids.filtered(lambda item: item.res_partner_id == self.user.partner_id)
        self.assertEqual(len(mine), 1)

    def test_a_mandatory_channel_cannot_be_turned_off(self):
        event = self.env["mail.message.subtype"].search([("code", "=", "invoice.sent")], limit=1)
        with self.assertRaises(UserError):
            self.env["medilab.notification.preference"].with_user(self.user).set_own(event, CHANNEL_EMAIL, False)

    def test_turning_email_off_skips_that_channel(self):
        self.env["medilab.notification.preference"].with_user(self.user).set_own(self.event, CHANNEL_EMAIL, False)
        task = self._task()
        message = self.env["mail.message"].raise_event(
            EVENT_TASK_REMINDER, task, "email-off", "Body", partners=self.user.partner_id
        )
        mine = message.notification_ids.filtered(lambda item: item.res_partner_id == self.user.partner_id)
        self.assertFalse(mine.mail_mail_id)

    def test_a_missing_email_is_logged_and_not_queued(self):
        partner = self.env["res.partner"].create({"name": "No email"})
        task = self._task()
        with self.assertLogs("odoo.addons.sol_laboratory.models.notifications.mail_message", level="WARNING") as logged:
            message = self.env["mail.message"].raise_event(
                EVENT_TASK_REMINDER, task, "no-email", "Body", partners=partner
            )
        self.assertFalse(message.notification_ids.filtered(lambda item: item.res_partner_id == partner).mail_mail_id)
        self.assertTrue(logged.output)

    def test_a_reminder_is_sent_once(self):
        person = self.env["medilab.person"].create({"name": "Assignee", "login": "assignee.reminder"})
        start = fields.Datetime.now() + timedelta(minutes=10)
        task = self.env["medilab.task"].create(
            {
                "type_id": self.task_type.id,
                "name": "Start soon",
                "assignee_id": person.id,
                "planned_start": start,
            }
        )
        event = self.env["calendar.event"].search([("medilab_task_id", "=", task.id)])
        self.assertTrue(event)
        self.assertFalse(event.alarm_ids)
        self.env["medilab.scheduled.job"]._run_key("notifications.remind")
        self.env["medilab.scheduled.job"]._run_key("notifications.remind")
        messages = self.env["mail.message"].search([("notification_key", "like", f"calendar:{event.id}:reminder:%")])
        self.assertEqual(len(messages), 1)

    def test_an_email_outage_leaves_one_mail_and_a_later_run_sends_it(self):
        self.user.notification_type = "email"
        task = self._task()
        self.env["mail.message"].raise_event(
            EVENT_TASK_REMINDER, task, "smtp-down", "Body", partners=self.user.partner_id
        )
        mail = self.env["mail.mail"].search([("email_to", "=", self.user.email)], order="id desc", limit=1)
        item = self.env["medilab.job.item"].search([("item_key", "=", f"mail:{mail.id}")], limit=1)
        job = item.job_id

        def down(self, auto_commit=False, raise_exception=False, post_send_callback=None):
            raise ConnectionError("smtp down")

        with patch("odoo.addons.mail.models.mail_mail.MailMail.send", down), self.assertRaises(ConnectionError):
            job._handle_notifications_email(item)
        self.assertEqual(mail.state, "outgoing")
        job._handle_notifications_email(item)
        self.assertNotEqual(mail.state, "exception")
        self.assertEqual(self.env["medilab.job.item"].search_count([("item_key", "=", f"mail:{mail.id}")]), 1)

    def test_a_rejected_token_turns_the_device_off_and_a_temporary_error_does_not(self):
        device = self.env["medilab.mobile.device"].with_user(self.user).register_token("token-1", "android")
        self.env["medilab.notification.preference"].with_user(self.user).set_own(self.event, "push", True)
        task = self._task()
        self.env["mail.message"].raise_event(EVENT_TASK_REMINDER, task, "push-1", "Body", partners=self.user.partner_id)
        delivery = self.env["medilab.push.delivery"].search([("mobile_device_id", "=", device.id)])
        client = FirebaseClient(object(), "project")

        def permanent(token, title, body):
            raise PermanentTokenError("UNREGISTERED")

        with (
            patch(
                "odoo.addons.sol_laboratory.models.notifications.scheduled_job.firebase_client_from_env",
                return_value=client,
            ),
            patch.object(client, "send", permanent),
        ):
            self.env["medilab.scheduled.job"]._run_key("notifications.push")
        self.assertFalse(device.active)
        self.assertEqual(delivery.status, "skipped")

        device2 = self.env["medilab.mobile.device"].with_user(self.user).register_token("token-2", "ios")
        self.env["mail.message"].raise_event(EVENT_TASK_REMINDER, task, "push-2", "Body", partners=self.user.partner_id)
        delivery2 = self.env["medilab.push.delivery"].search([("mobile_device_id", "=", device2.id)])

        def temporary(token, title, body):
            raise TemporaryFirebaseError("503")

        with (
            patch(
                "odoo.addons.sol_laboratory.models.notifications.scheduled_job.firebase_client_from_env",
                return_value=client,
            ),
            patch.object(client, "send", temporary),
        ):
            self.env["medilab.scheduled.job"]._run_key("notifications.push")
        self.assertTrue(device2.active)
        self.assertEqual(delivery2.status, "pending")

    def test_firebase_classifies_permanent_and_temporary_errors(self):
        client = FirebaseClient(object(), "project")
        permanent = _Response(404, {"error": {"status": "UNREGISTERED", "details": [{"errorCode": "UNREGISTERED"}]}})
        temporary = _Response(503, {"error": {"status": "UNAVAILABLE"}})
        invalid = _Response(
            400,
            {
                "error": {
                    "status": "INVALID_ARGUMENT",
                    "message": "The registration token is not a valid FCM registration token",
                }
            },
        )
        with self.assertRaises(PermanentTokenError):
            client._raise_for_response(permanent)
        with self.assertRaises(TemporaryFirebaseError):
            client._raise_for_response(temporary)
        with self.assertRaises(PermanentTokenError):
            client._raise_for_response(invalid)
        with self.assertRaises(PermanentTokenError):
            client._raise_for_response(_Response(400, {"error": {"details": [{"errorCode": "SENDER_ID_MISMATCH"}]}}))
        with self.assertRaises(TemporaryFirebaseError):
            client._raise_for_response(_JsonError(500, None))
        with self.assertRaises(TemporaryFirebaseError):
            client._raise_for_response(_Response(400, ["not-an-object"]))
        with self.assertRaises(TemporaryFirebaseError):
            client._raise_for_response(_Response(400, {"error": "unavailable"}))
        with self.assertRaises(TemporaryFirebaseError):
            client._raise_for_response(_Response(429, {"error": {"status": "RESOURCE_EXHAUSTED"}}))
        with self.assertRaises(TemporaryFirebaseError):
            client._raise_for_response(
                _Response(400, {"error": {"status": "INVALID_ARGUMENT", "message": "A field is missing"}})
            )

    def test_send_refreshes_a_token_and_a_dropped_connection_can_be_retried(self):
        credentials = _Credentials(valid=False)
        client = FirebaseClient(credentials, "project")
        with patch(
            "odoo.addons.sol_laboratory.services.firebase_client.requests.post",
            return_value=_Response(200, {}),
        ):
            client.send("token", "Title", "Body")
        self.assertTrue(credentials.refreshed)
        ready = FirebaseClient(_Credentials(), "project")
        with (
            patch(
                "odoo.addons.sol_laboratory.services.firebase_client.requests.post",
                side_effect=requests.RequestException("down"),
            ),
            self.assertRaises(TemporaryFirebaseError),
        ):
            ready.send("token", "Title", "Body")

    def test_a_client_is_built_from_credentials_or_left_unset(self):
        credentials = _Credentials()
        with patch.dict(os.environ, {FIREBASE_PROJECT_ID: "project", FIREBASE_CREDENTIALS: "not-json"}):
            self.assertIsNone(firebase_client.firebase_client_from_env())
        with (
            patch.dict(os.environ, {FIREBASE_PROJECT_ID: "project", FIREBASE_CREDENTIALS: "{}"}),
            patch.object(
                firebase_client.service_account.Credentials,
                "from_service_account_info",
                return_value=credentials,
            ),
        ):
            client = firebase_client.firebase_client_from_env()
        self.assertEqual(client.project_id, "project")
        absent = {FIREBASE_PROJECT_ID: "", FIREBASE_CREDENTIALS: ""}
        with (
            patch.dict(os.environ, absent),
            patch("google.auth.default", side_effect=Exception("missing")),
        ):
            self.assertIsNone(firebase_client.firebase_client_from_env())
        with (
            patch.dict(os.environ, absent),
            patch("google.auth.default", return_value=(credentials, "detected")),
        ):
            detected = firebase_client.firebase_client_from_env()
        self.assertEqual(detected.project_id, "detected")
        with (
            patch.dict(os.environ, {FIREBASE_PROJECT_ID: "from-env", FIREBASE_CREDENTIALS: ""}),
            patch("google.auth.default", return_value=(credentials, None)),
        ):
            from_env = firebase_client.firebase_client_from_env()
        self.assertEqual(from_env.project_id, "from-env")
        with (
            patch.dict(os.environ, absent),
            patch("google.auth.default", return_value=(None, None)),
        ):
            self.assertIsNone(firebase_client.firebase_client_from_env())

    def test_moving_or_deleting_the_event_updates_the_task(self):
        person = self.env["medilab.person"].create({"name": "Planner", "login": "planner.reminder"})
        start = fields.Datetime.now() + timedelta(minutes=20)
        task = self.env["medilab.task"].create(
            {
                "type_id": self.task_type.id,
                "name": "Move",
                "assignee_id": person.id,
                "planned_start": start,
            }
        )
        event = self.env["calendar.event"].search([("medilab_task_id", "=", task.id)])
        moved = start + timedelta(minutes=15)
        event.write({"start": moved, "stop": moved + timedelta(hours=1)})
        self.assertEqual(task.planned_start, event.start)
        self.assertEqual(task.planned_end, event.stop)
        event.unlink()
        self.assertFalse(task.planned_start)
        self.assertFalse(task.planned_end)

    def test_a_cancelled_email_is_not_retried(self):
        self.user.notification_type = "email"
        task = self._task()
        self.env["mail.message"].raise_event(
            EVENT_TASK_REMINDER, task, "cancelled-mail", "Body", partners=self.user.partner_id
        )
        mail = self.env["mail.mail"].search([("email_to", "=", self.user.email)], order="id desc", limit=1)
        item = self.env["medilab.job.item"].search([("item_key", "=", f"mail:{mail.id}")], limit=1)
        mail.sudo().write({"state": "cancel"})
        with self.assertRaises(PermanentJobError):
            item.job_id._handle_notifications_email(item)

    def test_a_push_is_sent_and_waits_when_firebase_is_not_configured(self):
        device = self.env["medilab.mobile.device"].with_user(self.user).register_token("token-sent", "android")
        self.env["medilab.notification.preference"].with_user(self.user).set_own(self.event, "push", True)
        task = self._task()
        self.env["mail.message"].raise_event(
            EVENT_TASK_REMINDER, task, "push-sent", "Body", partners=self.user.partner_id
        )
        delivery = self.env["medilab.push.delivery"].search([("mobile_device_id", "=", device.id)])
        item = self.env["medilab.job.item"].search([("item_key", "=", f"delivery:{delivery.id}")], limit=1)
        client = FirebaseClient(_Credentials(), "project")
        with (
            patch(
                "odoo.addons.sol_laboratory.models.notifications.scheduled_job.firebase_client_from_env",
                return_value=client,
            ),
            patch.object(client, "send"),
        ):
            self.assertIsNone(item.job_id._handle_notifications_push(item))
        self.assertEqual(delivery.status, "sent")

        waiting = self.env["medilab.mobile.device"].with_user(self.user).register_token("token-wait", "ios")
        self.env["mail.message"].raise_event(
            EVENT_TASK_REMINDER, task, "push-wait", "Body", partners=self.user.partner_id
        )
        delivery = self.env["medilab.push.delivery"].search([("mobile_device_id", "=", waiting.id)])
        item = self.env["medilab.job.item"].search([("item_key", "=", f"delivery:{delivery.id}")], limit=1)
        with patch(
            "odoo.addons.sol_laboratory.models.notifications.scheduled_job.firebase_client_from_env",
            return_value=None,
        ):
            self.assertTrue(item.job_id._handle_notifications_push(item))
        self.assertEqual(delivery.status, "pending")
        waiting.active = False
        self.assertIsNone(item.job_id._handle_notifications_push(item))
        self.assertEqual(delivery.status, "skipped")

    def _task(self):
        department = self.env["hr.department"].create({"name": "Notify"})
        return self.env["medilab.task"].create(
            {"type_id": self.task_type.id, "name": "Notify", "department_id": department.id}
        )


@tagged("post_install", "-at_install")
class TestBrevoWebhook(HttpCase):
    def test_a_missing_token_rejects_the_webhook(self):
        with patch.dict(os.environ, {BREVO_WEBHOOK_TOKEN: ""}):
            response = self.url_open(
                "/medilab/brevo/webhook",
                data=b"{}",
                headers={"Content-Type": "application/json", "Authorization": "Bearer secret"},
            )
        self.assertEqual(response.status_code, 401)

    def test_a_body_that_is_not_json_is_rejected(self):
        with patch.dict(os.environ, {BREVO_WEBHOOK_TOKEN: "secret"}):
            response = self.url_open(
                "/medilab/brevo/webhook",
                data=b"not-json",
                headers={"Content-Type": "application/json", "Authorization": "Bearer secret"},
            )
        self.assertEqual(response.status_code, 400)

    def test_a_bounce_flags_only_the_matched_partner(self):
        with patch.dict(os.environ, {BREVO_WEBHOOK_TOKEN: "secret"}):
            self._bounce_only_the_matched_partner()

    def _bounce_only_the_matched_partner(self):
        partner = self.env["res.partner"].create({"name": "Bounced", "email": "bounced@example.com"})
        other = self.env["res.partner"].create({"name": "Other", "email": "other@example.com"})
        task_type = self.env["medilab.task.type"].search([], limit=1)
        department = self.env["hr.department"].create({"name": "Bounce"})
        task = self.env["medilab.task"].create(
            {"type_id": task_type.id, "name": "Bounce", "department_id": department.id}
        )
        message = self.env["mail.message"].raise_event("task.reminder", task, "bounce-1", "Body", partners=partner)
        notification = message.notification_ids.filtered(lambda item: item.res_partner_id == partner)
        self.assertEqual(len(notification), 1)
        response = self.url_open(
            "/medilab/brevo/webhook",
            data=(
                '{"event":"hardBounce","email":"bounced@example.com","X-Mailin-custom":"notification:%s"}'
                % notification.id
            ).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer secret"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(partner.email_bounced)
        self.assertFalse(other.email_bounced)
        self.assertEqual(notification.brevo_status, "bounced")
        again = self.url_open(
            "/medilab/brevo/webhook",
            data=(
                '{"event":"delivered","email":"bounced@example.com","X-Mailin-custom":"notification:%s"}'
                % notification.id
            ).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer secret"},
        )
        self.assertEqual(again.status_code, 200)
        self.assertEqual(notification.brevo_status, "bounced")
        wrong = self.url_open(
            "/medilab/brevo/webhook",
            data=(
                '{"event":"hardBounce","email":"other@example.com","X-Mailin-custom":"notification:%s"}'
                % notification.id
            ).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer secret"},
        )
        self.assertEqual(wrong.status_code, 200)
        self.assertFalse(other.email_bounced)
