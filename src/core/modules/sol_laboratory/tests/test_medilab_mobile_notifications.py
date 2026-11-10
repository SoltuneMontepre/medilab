from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from .laboratory_api_case import LaboratoryApiCase
from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.laboratory_files import NOT_FOUND
from odoo.addons.sol_laboratory.constants.medilab_mobile import MANDATORY_EVENT
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_DEVICE,
    MODEL_MAIL_MESSAGE,
    MODEL_MAIL_MESSAGE_SUBTYPE,
    MODEL_MAIL_NOTIFICATION,
    MODEL_MOBILE_DEVICE,
    MODEL_NOTIFICATION_PREFERENCE,
    MODEL_PUSH_DELIVERY,
    MODEL_SCHEDULED_JOB,
    MODEL_TASK,
)
from odoo.addons.sol_laboratory.constants.notifications import (
    CHANNEL_PUSH,
    EVENT_DOCUMENT_LOCK_RELEASED,
    EVENT_SAMPLE_INSUFFICIENT,
    EVENT_TASK_REMINDER,
    EVENT_TEST_RESULT_REJECTED,
)
from odoo.addons.sol_laboratory.services.document_code import document_code
from odoo.addons.sol_laboratory.services.firebase_client import FirebaseClient

SAMPLE_READER_GROUP = "sol_laboratory.group_permission_sample_read_all"
FIREBASE = "odoo.addons.sol_laboratory.models.notifications.scheduled_job.firebase_client_from_env"


@tagged("post_install", "-at_install")
class TestMedilabMobileNotifications(LaboratoryApiCase, RequestCase):
    """Pushes, notifications, push preferences and documents of a person signed in on Medilab Mobile."""

    def setUp(self):
        super().setUp()
        self.person = self.colleague
        self.person.notification_type = "inbox"
        self.key = self.signed_in_key(self.person, "phone", name="Pixel 8", platform="android")
        self.assertEqual(self.api("PUT", "/push-token", {"token": "fcm-token"}, key=self.key).status_code, 204)
        self.phone = self.env[MODEL_LABORATORY_DEVICE].search([("client_uid", "=", "phone")])
        self.token = self.env[MODEL_MOBILE_DEVICE].search([("laboratory_device_id", "=", self.phone.id)])

    def notify(self, code, document, key, **values):
        return self.env[MODEL_MAIL_MESSAGE].raise_event(
            code, document, key, "Body", partners=self.person.partner_id, **values
        )

    def deliveries(self, message):
        return self.env[MODEL_PUSH_DELIVERY].search([("notification_id.mail_message_id", "=", message.id)])

    def push_all(self):
        """Run the push job against a Firebase that accepts every push, and the pushes it sent."""
        client = FirebaseClient(object(), "project")
        sent = []
        with patch(FIREBASE, return_value=client), patch.object(client, "send", lambda *push: sent.append(push)):
            self.env[MODEL_SCHEDULED_JOB]._run_key("notifications.push")
        return sent

    def task(self, **values):
        return self.env[MODEL_TASK].create(
            {
                "type_id": self.env.ref("sol_laboratory.task_type_general").id,
                "name": "Call the customer",
                "department_id": self.department.id,
                **values,
            }
        )

    # Pushes

    def test_a_push_names_the_event_and_the_lab_code_and_never_the_customer(self):
        self.notify(
            EVENT_SAMPLE_INSUFFICIENT,
            self.sample,
            "insufficient",
            subject=f"{self.customer.name}: {self.sample.customer_sample_name}",
        )

        [(token, title, body, data)] = self.push_all()

        self.assertEqual((token, title, body), ("fcm-token", "Sample insufficient", self.sample.code))
        self.assertEqual(
            data,
            {
                "event": EVENT_SAMPLE_INSUFFICIENT,
                "model": self.sample._name,
                "id": str(self.sample.id),
                "code": self.sample.code,
            },
        )
        pushed = " ".join([title, body, *data.values()])
        self.assertNotIn(self.customer.name, pushed)
        self.assertNotIn(self.sample.customer_sample_name, pushed)

    def test_a_push_names_a_sample_test_and_its_task_by_the_sample_lab_code(self):
        test = self.sample.test_ids
        task = self.task(document_model=test._name, document_id=test.id)

        self.assertEqual(document_code(test), self.sample.code)
        self.assertEqual(document_code(task), self.sample.code)
        self.assertEqual(document_code(self.task()), "")

    def test_a_push_title_is_in_the_person_language(self):
        self.env["res.lang"]._activate_lang("vi_VN")
        self.person.lang = "vi_VN"
        event = self.env[MODEL_MAIL_MESSAGE_SUBTYPE]._event(EVENT_SAMPLE_INSUFFICIENT)
        self.notify(EVENT_SAMPLE_INSUFFICIENT, self.sample, "insufficient-vi")

        [(_token, title, _body, _data)] = self.push_all()

        self.assertEqual(title, event.with_context(lang="vi_VN").name)

    def test_every_event_is_pushed_by_default_and_a_push_turned_off_on_the_phone_is_no_longer_sent(self):
        task = self.task()
        self.assertTrue(self.deliveries(self.notify(EVENT_TASK_REMINDER, task, "before")))

        response = self.api("PUT", f"/notification-preferences/{EVENT_TASK_REMINDER}", {"push": False}, key=self.key)

        self.assertEqual(response.json()["push"], False)
        self.assertFalse(self.deliveries(self.notify(EVENT_TASK_REMINDER, task, "after")))
        preference = self.env[MODEL_NOTIFICATION_PREFERENCE].search(
            [("user_id", "=", self.person.id), ("channel", "=", CHANNEL_PUSH)]
        )
        self.assertEqual((preference.event_id.code, preference.enabled), (EVENT_TASK_REMINDER, False))

    def test_the_push_of_a_mandatory_event_cannot_be_turned_off(self):
        response = self.api(
            "PUT", f"/notification-preferences/{EVENT_TEST_RESULT_REJECTED}", {"push": False}, key=self.key
        )

        self.assertApiRefused(MANDATORY_EVENT, response)
        event = self.env[MODEL_MAIL_MESSAGE_SUBTYPE]._event(EVENT_TEST_RESULT_REJECTED)
        preferences = self.env[MODEL_NOTIFICATION_PREFERENCE].with_user(self.person)
        with self.assertRaises(UserError):
            preferences.set_own(event, CHANNEL_PUSH, False)
        # A push turned off before mandatory events were kept on is ignored.
        preferences.sudo().create(
            {"user_id": self.person.id, "event_id": event.id, "channel": CHANNEL_PUSH, "enabled": False}
        )
        self.assertTrue(self.deliveries(self.notify(EVENT_TEST_RESULT_REJECTED, self.task(), "rejected")))

    def test_pushes_reach_only_phones_still_signed_in(self):
        task = self.task()
        message = self.notify(EVENT_TASK_REMINDER, task, "signed-in")

        self.assertEqual(self.api("POST", "/sign-out", key=self.key).status_code, 204)

        self.assertFalse(self.push_all())
        self.assertEqual(self.deliveries(message).status, "skipped")
        self.assertFalse(self.deliveries(self.notify(EVENT_TASK_REMINDER, task, "signed-out")))

    def test_a_revoked_phone_gets_no_push_even_with_its_token_on(self):
        self.phone.action_revoke()
        self.token.sudo().active = True

        self.assertFalse(self.deliveries(self.notify(EVENT_TASK_REMINDER, self.task(), "revoked")))

    # Push preferences

    def test_the_preferences_list_every_event_with_its_push(self):
        lock = self.env[MODEL_MAIL_MESSAGE_SUBTYPE]._event(EVENT_DOCUMENT_LOCK_RELEASED)
        lock.enabled = False
        self.api("PUT", f"/notification-preferences/{EVENT_TASK_REMINDER}", {"push": False}, key=self.key)

        preferences = {
            preference["event"]: preference
            for preference in self.api("GET", "/notification-preferences", key=self.key).json()["preferences"]
        }

        self.assertEqual(
            preferences[EVENT_TASK_REMINDER],
            {"event": EVENT_TASK_REMINDER, "name": "Task reminder", "mandatory": False, "push": False},
        )
        self.assertEqual((preferences[EVENT_SAMPLE_INSUFFICIENT]["push"]), True)
        self.assertEqual(
            (preferences[EVENT_TEST_RESULT_REJECTED]["mandatory"], preferences[EVENT_TEST_RESULT_REJECTED]["push"]),
            (True, True),
        )
        self.assertNotIn(EVENT_DOCUMENT_LOCK_RELEASED, preferences)
        self.assertApiRefused(
            NOT_FOUND,
            self.api("PUT", f"/notification-preferences/{EVENT_DOCUMENT_LOCK_RELEASED}", {"push": False}, key=self.key),
        )
        self.assertApiRefused(
            NOT_FOUND, self.api("PUT", "/notification-preferences/no.such.event", {"push": True}, key=self.key)
        )

    def test_turning_a_push_on_again_on_the_phone_sends_it_again(self):
        path = f"/notification-preferences/{EVENT_TASK_REMINDER}"
        self.api("PUT", path, {"push": False}, key=self.key)

        self.assertEqual(self.api("PUT", path, {"push": True}, key=self.key).json()["push"], True)

        self.assertTrue(self.deliveries(self.notify(EVENT_TASK_REMINDER, self.task(), "on-again")))

    # Notifications

    def test_notifications_are_listed_unread_first_then_newest_and_page_by_page(self):
        task = self.task()
        oldest = self.notify(EVENT_TASK_REMINDER, task, "oldest")
        read = self.notify(EVENT_TASK_REMINDER, task, "read")
        newest = self.notify(EVENT_TASK_REMINDER, task, "newest")
        self.assertEqual(self.api("POST", f"/notifications/{read.id}/read", key=self.key).status_code, 204)

        first = self.api("GET", "/notifications?limit=2", key=self.key).json()
        rest = self.api("GET", f"/notifications?after={first['next_after']}&limit=2", key=self.key).json()

        listed = first["notifications"] + rest["notifications"]
        self.assertEqual([item["id"] for item in listed], [newest.id, oldest.id, read.id])
        self.assertEqual([item["read"] for item in listed], [False, False, True])
        self.assertIsNone(rest["next_after"])
        self.assertEqual(
            listed[0],
            {
                "id": newest.id,
                "event": EVENT_TASK_REMINDER,
                "title": "Task reminder",
                "date": listed[0]["date"],
                "read": False,
                "document": {"model": MODEL_TASK, "id": task.id, "code": ""},
            },
        )

    def test_reading_a_notification_on_the_phone_reads_it_on_the_web(self):
        message = self.notify(EVENT_SAMPLE_INSUFFICIENT, self.sample, "read-on-web")

        self.assertEqual(self.api("POST", f"/notifications/{message.id}/read", key=self.key).status_code, 204)
        self.assertEqual(self.api("POST", f"/notifications/{message.id}/read", key=self.key).status_code, 204)

        notification = self.env[MODEL_MAIL_NOTIFICATION].search(
            [("mail_message_id", "=", message.id), ("res_partner_id", "=", self.person.partner_id.id)]
        )
        self.assertTrue(notification.is_read)

    def test_a_notification_of_someone_else_is_not_found(self):
        message = self.env[MODEL_MAIL_MESSAGE].raise_event(
            EVENT_TASK_REMINDER, self.task(), "someone-else", "Body", partners=self.tester.partner_id
        )

        self.assertApiRefused(NOT_FOUND, self.api("POST", f"/notifications/{message.id}/read", key=self.key))
        self.assertEqual(self.api("GET", "/notifications", key=self.key).json()["notifications"], [])
        self.assertApiRefused(
            NOT_FOUND, self.api("GET", f"/notifications?after={message.notification_ids[:1].id}", key=self.key)
        )

    # Documents

    def test_a_document_opens_on_its_screen_with_its_code(self):
        self.person.group_ids = [Command.link(self.env.ref(SAMPLE_READER_GROUP).id)]

        document = self.api("GET", f"/documents/{self.sample._name}/{self.sample.id}", key=self.key).json()

        self.assertEqual(
            document,
            {
                "model": self.sample._name,
                "id": self.sample.id,
                "code": self.sample.code,
                "title": self.sample.code,
                "screen": "sample",
                "url": f"{self.sample.get_base_url()}/odoo/{self.sample._name}/{self.sample.id}",
            },
        )

    def test_a_document_the_person_can_no_longer_see_is_not_found(self):
        path = f"/documents/{self.sample._name}/{self.sample.id}"
        self.person.group_ids = [Command.link(self.env.ref(SAMPLE_READER_GROUP).id)]
        self.assertEqual(self.api("GET", path, key=self.key).status_code, 200)

        self.person.group_ids = [Command.unlink(self.env.ref(SAMPLE_READER_GROUP).id)]

        self.assertApiRefused(NOT_FOUND, self.api("GET", path, key=self.key))
        self.assertApiRefused(NOT_FOUND, self.api("GET", f"/documents/{self.sample._name}/999999999", key=self.key))
        self.assertApiRefused(NOT_FOUND, self.api("GET", "/documents/no.such.model/1", key=self.key))
        self.assertApiRefused(NOT_FOUND, self.api("GET", "/documents/medilab.task.reassign/1", key=self.key))

    def test_a_document_without_a_screen_of_its_own_opens_on_the_web(self):
        partner = self.person.partner_id

        document = self.api("GET", f"/documents/res.partner/{partner.id}", key=self.key).json()

        self.assertEqual((document["screen"], document["code"], document["title"]), ("web", "", partner.display_name))
