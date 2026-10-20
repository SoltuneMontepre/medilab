import os
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import mute_logger

from .audit_case import AuditLookup
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_ENTRY,
    MODEL_DEPARTMENT,
    MODEL_JOB_ITEM,
    MODEL_MAIL_MAIL,
    MODEL_MAIL_MESSAGE,
    MODEL_MAIL_MESSAGE_SUBTYPE,
    MODEL_MOBILE_DEVICE,
    MODEL_NOTIFICATION_PREFERENCE,
    MODEL_PUSH_DELIVERY,
    MODEL_TASK,
    MODEL_TASK_TYPE,
)
from odoo.addons.sol_laboratory.constants.notifications import BREVO_WEBHOOK_TOKEN, CHANNEL_PUSH, EVENT_TASK_REMINDER
from odoo.addons.sol_laboratory.services.firebase_client import FirebaseClient, PermanentTokenError

FIREBASE_FROM_ENV = "odoo.addons.sol_laboratory.models.notifications.scheduled_job.firebase_client_from_env"
MAIL_SERVER = "odoo.addons.base.models.ir_mail_server.IrMail_Server"
BREVO_HEADERS = {"Content-Type": "application/json", "Authorization": "Bearer secret"}


@contextmanager
def mail_server(**send_email):
    # Odoo sends no email during tests. This server takes each email as send_email says.
    with (
        patch(f"{MAIL_SERVER}._disable_send", return_value=False),
        patch(f"{MAIL_SERVER}._connect__", return_value=MagicMock()),
        patch(f"{MAIL_SERVER}.send_email", **send_email),
    ):
        yield


@tagged("post_install", "-at_install")
class TestAuditIntegrations(AuditLookup, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.recipient = new_test_user(
            cls.env, login="recipient", email="recipient@example.com", notification_type="email"
        )
        department = cls.env[MODEL_DEPARTMENT].create({"name": "Integrations"})
        cls.task = cls.env[MODEL_TASK].create(
            {
                "type_id": cls.env[MODEL_TASK_TYPE].search([], limit=1).id,
                "name": "Calibrate the balance",
                "department_id": department.id,
            }
        )

    def notify(self, key):
        return self.env[MODEL_MAIL_MESSAGE].raise_event(
            EVENT_TASK_REMINDER, self.task, key, "Body", subject="Calibration", partners=self.recipient.partner_id
        )

    def email(self, key):
        self.notify(key)
        return self.env[MODEL_MAIL_MAIL].search([("email_to", "=", self.recipient.email)], order="id desc", limit=1)

    def events(self, action):
        # Entries without a document, such as a webhook refused before it names one.
        return self.env[MODEL_AUDIT_ENTRY].sudo().search([("action", "=", action), ("document_model", "=", False)])

    def test_a_sent_email_is_recorded_on_its_document(self):
        mail = self.email("sent")

        with mail_server(return_value="<sent@example.com>"):
            mail.send()

        entry = self.entries(self.task, "integration")
        self.assertEqual(entry.note, "Email sent: Calibration")

    def test_an_email_the_server_refuses_is_an_error_on_its_document(self):
        mail = self.email("refused")

        with (
            mail_server(side_effect=ValueError("Mailbox unavailable")),
            mute_logger("odoo.addons.mail.models.mail_mail"),
        ):
            mail.send(raise_exception=False)

        self.assertIn("Mailbox unavailable", self.entries(self.task, "error").note)
        self.assertFalse(self.entries(self.task, "integration"))

    def test_a_brevo_event_is_recorded_on_the_document_of_its_email(self):
        message = self.notify("delivered")
        notification = message.notification_ids.filtered(lambda item: item.res_partner_id == self.recipient.partner_id)
        body = f'{{"event":"delivered","email":"{self.recipient.email}","X-Mailin-custom":"notification:{notification.id}"}}'

        with patch.dict(os.environ, {BREVO_WEBHOOK_TOKEN: "secret"}):
            self.url_open("/medilab/brevo/webhook", data=body.encode(), headers=BREVO_HEADERS)

        entry = self.entries(self.task, "integration")
        self.assertEqual(entry.note, f"Brevo reported delivered for {self.recipient.partner_id.display_name}")
        self.assertEqual((entry.source, entry.user_id.id), ("api", False))

    def test_a_refused_brevo_webhook_is_an_error_from_nobody(self):
        with patch.dict(os.environ, {BREVO_WEBHOOK_TOKEN: "secret"}):
            self.url_open("/medilab/brevo/webhook", data=b"{}", headers={"Authorization": "Bearer wrong"})
            self.url_open("/medilab/brevo/webhook", data=b"not-json", headers=BREVO_HEADERS)

        errors = self.events("error")
        self.assertEqual(
            set(errors.mapped("note")),
            {"Brevo webhook refused: the token does not match", "Brevo webhook refused: the body is not JSON"},
        )
        self.assertEqual(set(errors.mapped("source")), {"api"})
        self.assertFalse(errors.user_id)

    def test_a_push_is_recorded_on_its_document_and_a_rejected_token_on_the_device(self):
        devices = self.env[MODEL_MOBILE_DEVICE].with_user(self.recipient)
        sent, rejected = devices.register_token("token-sent", "android"), devices.register_token("token-gone", "ios")
        event = self.env[MODEL_MAIL_MESSAGE_SUBTYPE]._event(EVENT_TASK_REMINDER)
        self.env[MODEL_NOTIFICATION_PREFERENCE].with_user(self.recipient).set_own(event, CHANNEL_PUSH, True)
        self.notify("push")
        client = FirebaseClient(object(), "project")

        def send(token, title, body):
            if token == "token-gone":
                raise PermanentTokenError("UNREGISTERED")

        with patch(FIREBASE_FROM_ENV, return_value=client), patch.object(client, "send", send):
            for device in sent | rejected:
                delivery = self.env[MODEL_PUSH_DELIVERY].search([("mobile_device_id", "=", device.id)])
                item = self.env[MODEL_JOB_ITEM].search([("item_key", "=", f"delivery:{delivery.id}")])
                item.job_id._handle_notifications_push(item)

        self.assertEqual(self.entries(self.task, "integration").note, f"Push sent to {self.recipient.name} on android")
        self.assertEqual(self.entries(rejected, "error").note, "Firebase rejected the token: UNREGISTERED")
