from odoo.tests import new_test_user, tagged

from .laboratory_api_case import LaboratoryApiCase
from .mobile_phones import phone_person, push_token
from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.laboratory_files import INVALID_REQUEST, NOT_FOUND
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MAIL_MAIL,
    MODEL_MAIL_MESSAGE,
    MODEL_MAIL_NOTIFICATION,
    MODEL_PUSH_DELIVERY,
    MODEL_TASK,
)


@tagged("post_install", "-at_install")
class TestMedilabMobileChatter(LaboratoryApiCase, RequestCase):
    """The chatter of a customer's sample, its test request and a task, read and noted on the phone by a tester of the
    sample's department, who never sees the customer, while the customer follows the test request."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.chemist = phone_person(cls.env, "Nguyen Van An", "an.chatter", cls.department, ("sample_read_all",))
        cls.head = phone_person(cls.env, "Tran Thi Binh", "binh.chatter", cls.department, ("sample_read_all",))
        cls.portal = new_test_user(cls.env, login="customer.chatter", groups="base.group_portal")
        cls.request.message_subscribe(partner_ids=cls.portal.partner_id.ids)
        cls.sample.message_subscribe(partner_ids=cls.portal.partner_id.ids)
        cls.head.user_id.notification_type = "inbox"
        push_token(cls.env, cls.head.user_id, "fcm-head")

    def setUp(self):
        super().setUp()
        self.key = self.signed_in_key(self.chemist.user_id, "chemist-phone", name="Pixel 8", platform="android")

    def on_phone(self, method, path, body=None, headers=None):
        return self.api(method, path, body, key=self.key, headers=headers)

    def answered(self, response) -> dict:
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def note_on_sample(self, text="Bottle cap was loose", mentions=(), key="note-1"):
        body = {"text": text, "mentions": list(mentions)}
        path = f"/documents/medilab.sample/{self.sample.id}/notes"
        return self.answered(self.on_phone("POST", path, body, headers={"Idempotency-Key": key}))

    def test_a_note_from_the_phone_reaches_nobody_outside_the_laboratory(self):
        note = self.note_on_sample(mentions=[self.head.user_id.id])

        self.assertEqual(self.note_on_sample(mentions=[self.head.user_id.id])["id"], note["id"])
        message = self.env[MODEL_MAIL_MESSAGE].browse(note["id"])
        self.assertTrue(note["note"])
        self.assertEqual(message.subtype_id, self.env.ref("mail.mt_note"))
        self.assertEqual(
            (message.model, message.res_id, message.author_id),
            (self.sample._name, self.sample.id, self.chemist.user_id.partner_id),
        )
        notified = self.env[MODEL_MAIL_NOTIFICATION].search([("mail_message_id", "=", message.id)]).res_partner_id
        self.assertEqual(notified, self.head.user_id.partner_id)
        self.assertFalse(
            self.env[MODEL_MAIL_MAIL].search(
                [("mail_message_id", "=", message.id), ("recipient_ids", "in", self.portal.partner_id.ids)]
            )
        )

    def test_a_mention_in_a_note_is_pushed_without_its_text(self):
        note = self.note_on_sample(text="Customer called about this", mentions=[self.head.user_id.id])

        delivery = self.env[MODEL_PUSH_DELIVERY].search([("message_id", "=", note["id"])])
        self.assertEqual(delivery.mobile_device_id.user_id, self.head.user_id)
        title, body, data = delivery._push_message()
        self.assertEqual((title, body), ("Mention", self.sample.code))
        self.assertEqual(data["event"], "message.mention")
        self.assertEqual((data["model"], data["id"]), (self.sample._name, str(self.sample.id)))
        self.assertNotIn("Customer", f"{title} {body} {data}")

    def test_the_chatter_shows_what_people_wrote_on_the_document(self):
        written = self.sample.with_user(self.head.user_id).message_post(
            body="Re-run the blank", message_type="comment", subtype_xmlid="mail.mt_note"
        )
        self.sample.message_post(body="Status changed", message_type="notification")

        messages = self.answered(self.on_phone("GET", f"/documents/medilab.sample/{self.sample.id}/messages"))[
            "messages"
        ]

        self.assertEqual(
            [(message["id"], message["text"], message["author"]) for message in messages],
            [(written.id, "Re-run the blank", "Tran Thi Binh")],
        )

    def test_a_test_request_is_noted_by_who_reads_it_and_a_task_by_its_assignee(self):
        reader = phone_person(
            self.env, "Vo Thi Hanh", "hanh.chatter", None, ("test_request_read_all", "customer_read_all")
        )
        reader_key = self.signed_in_key(reader.user_id, "reader-phone", name="Pixel 7", platform="android")
        task = self.env[MODEL_TASK].create(
            {
                "type_id": self.env.ref("sol_laboratory.task_type_general").id,
                "name": "Call the customer",
                "department_id": self.department.id,
                "assignee_id": self.chemist.id,
            }
        )
        request_notes = f"/documents/medilab.test.request/{self.request.id}/notes"

        self.assertApiRefused(NOT_FOUND, self.on_phone("POST", request_notes, {"text": "Checked"}))
        self.assertEqual(
            self.answered(self.api("POST", request_notes, {"text": "Checked"}, key=reader_key))["text"], "Checked"
        )
        noted = self.answered(self.on_phone("POST", f"/documents/medilab.task/{task.id}/notes", {"text": "Called"}))
        self.assertEqual(self.env[MODEL_MAIL_MESSAGE].browse(noted["id"]).res_id, task.id)

    def test_a_document_without_a_chatter_on_the_phone_or_one_the_person_may_not_read_is_not_found(self):
        stranger = self.signed_in_key(self.colleague, "colleague-phone", name="Pixel 7", platform="android")

        self.assertApiRefused(
            NOT_FOUND, self.on_phone("GET", f"/documents/res.partner/{self.portal.partner_id.id}/messages")
        )
        self.assertApiRefused(
            NOT_FOUND, self.api("GET", f"/documents/medilab.sample/{self.sample.id}/messages", key=stranger)
        )

    def test_a_note_mentions_only_people_of_the_laboratory(self):
        path = f"/documents/medilab.sample/{self.sample.id}/notes"

        refused = self.on_phone("POST", path, {"text": "Ask them", "mentions": [self.portal.id]})

        self.assertApiRefused(INVALID_REQUEST, refused)
