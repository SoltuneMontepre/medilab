import base64
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import new_test_user, tagged

from .laboratory_api_case import LaboratoryApiCase
from .mobile_phones import push_token
from odoo.addons.sol_laboratory.constants.laboratory_files import INVALID_REQUEST, NOT_FOUND
from odoo.addons.sol_laboratory.constants.medilab_mobile import TOO_LARGE
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DISCUSS_CHANNEL,
    MODEL_DISCUSS_CHANNEL_MEMBER,
    MODEL_IR_CRON_TRIGGER,
    MODEL_MAIL_MESSAGE,
    MODEL_MAIL_MESSAGE_SUBTYPE,
    MODEL_MAIL_NOTIFICATION,
    MODEL_NOTIFICATION_PREFERENCE,
    MODEL_PUSH_DELIVERY,
    MODEL_RES_PARTNER,
)
from odoo.addons.sol_laboratory.constants.notifications import CHANNEL_EMAIL, CHANNEL_PUSH, EVENT_MESSAGE_MENTION

MESSAGES = "odoo.addons.sol_laboratory.services.mobile_messages"


@tagged("post_install", "-at_install")
class TestMedilabMobileConversations(LaboratoryApiCase):
    """Direct and group conversations of three people of the laboratory, one on the phone and two on the web with a
    phone each, and a customer who never joins one."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = new_test_user(cls.env, login="customer.portal", groups="base.group_portal")
        cls.tokens = {
            user: push_token(cls.env, user, f"fcm-{user.login}") for user in (cls.member, cls.colleague, cls.tester)
        }

    def setUp(self):
        super().setUp()
        self.key = self.signed_in_key(self.tester, "phone", name="Pixel 8", platform="android")

    def on_phone(self, method, path, body=None, key=None, headers=None):
        return self.api(method, path, body, key=key or self.key, headers=headers)

    def answered(self, response) -> dict:
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def group(self, key="group-1", name="Pesticides morning shift"):
        body = {"name": name, "member_ids": [self.member.id, self.colleague.id]}
        return self.answered(self.on_phone("POST", "/conversations", body, headers={"Idempotency-Key": key}))

    def channel(self, conversation):
        return self.env[MODEL_DISCUSS_CHANNEL].browse(conversation["id"])

    def pushed(self, message):
        return self.env[MODEL_PUSH_DELIVERY].search([("message_id", "=", message.id)]).mobile_device_id.user_id

    def message(self, answer):
        return self.env[MODEL_MAIL_MESSAGE].browse(answer["id"])

    # Conversations

    def test_a_group_is_created_once_per_key_with_the_person_and_its_members(self):
        conversation = self.group()

        self.assertEqual(self.group()["id"], conversation["id"])
        channel = self.channel(conversation)
        self.assertEqual(channel.channel_type, "group")
        self.assertEqual(channel.channel_member_ids.partner_id, (self.tester | self.member | self.colleague).partner_id)
        self.assertEqual(conversation["name"], "Pesticides morning shift")
        self.assertEqual(
            {member["id"] for member in conversation["members"]}, {self.tester.id, self.member.id, self.colleague.id}
        )

    def test_a_direct_conversation_is_the_one_discuss_opens_on_the_web(self):
        opened = self.answered(self.on_phone("POST", "/conversations", {"person_id": self.member.id}))

        web = self.env[MODEL_DISCUSS_CHANNEL].with_user(self.member)._get_or_create_chat([self.tester.partner_id.id])
        self.assertEqual(opened["id"], web.id)
        self.assertEqual((opened["type"], opened["name"]), ("chat", self.member.name))

    def test_the_list_gives_unread_messages_and_the_last_one(self):
        conversation = self.group()
        self.channel(conversation).with_user(self.member).message_post(body="Spinach is ready", message_type="comment")

        listed = self.answered(self.on_phone("GET", "/conversations"))["conversations"]

        self.assertEqual([item["id"] for item in listed], [conversation["id"]])
        self.assertEqual(listed[0]["unread"], 1)
        self.assertFalse(listed[0]["muted"])
        self.assertEqual(listed[0]["last_message"]["text"], "Spinach is ready")
        self.assertFalse(listed[0]["last_message"]["mine"])

    def test_a_conversation_the_person_is_not_in_is_not_found(self):
        channel = self.env[MODEL_DISCUSS_CHANNEL].with_user(self.member)._create_group(self.member | self.colleague)
        outsider = self.signed_in_key(self.outsider, "outsider-phone", name="Pixel 7", platform="android")

        self.assertApiRefused(NOT_FOUND, self.on_phone("GET", f"/conversations/{channel.id}/messages", key=outsider))
        self.assertApiRefused(
            NOT_FOUND, self.on_phone("POST", f"/conversations/{channel.id}/messages", {"text": "Hi"}, key=outsider)
        )

    # Only people of the laboratory

    def test_a_customer_or_a_contact_cannot_join_a_conversation_on_the_web_or_the_phone(self):
        channel = self.channel(self.group())
        contact = self.env[MODEL_RES_PARTNER].create({"name": "Subcontractor lab"})
        for partner in (self.customer.partner_id, contact):
            with self.subTest(partner=partner.name), self.assertRaises(ValidationError):
                channel._add_members(partners=partner)
        self.assertApiRefused(INVALID_REQUEST, self.on_phone("POST", "/conversations", {"person_id": self.customer.id}))
        refused = self.on_phone(
            "POST",
            "/conversations",
            {"member_ids": [self.member.id, self.customer.id]},
            headers={"Idempotency-Key": "g"},
        )
        self.assertApiRefused(INVALID_REQUEST, refused)
        self.assertFalse(
            self.env[MODEL_DISCUSS_CHANNEL_MEMBER].search([("partner_id", "=", self.customer.partner_id.id)])
        )

    def test_people_are_the_other_active_people_of_the_laboratory(self):
        people = self.answered(self.on_phone("GET", "/people?q=lab."))["people"]

        ids = {person["id"] for person in people}
        self.assertIn(self.member.id, ids)
        self.assertNotIn(self.tester.id, ids)
        self.assertEqual(self.answered(self.on_phone("GET", "/people?q=customer"))["people"], [])

    # Messages

    def test_messages_cross_between_the_phone_and_discuss_on_the_web(self):
        conversation = self.group()
        channel = self.channel(conversation)
        data = base64.b64encode(b"%PDF-1.7 worksheet").decode()
        body = {
            "text": "Worksheet attached",
            "files": [{"name": "worksheet.pdf", "mimetype": "application/pdf", "data": data}],
        }
        path = f"/conversations/{channel.id}/messages"

        sent = self.answered(self.on_phone("POST", path, body, headers={"Idempotency-Key": "m-1"}))

        self.assertEqual(
            self.answered(self.on_phone("POST", path, body, headers={"Idempotency-Key": "m-1"}))["id"], sent["id"]
        )
        on_web = self.env[MODEL_MAIL_MESSAGE].with_user(self.member)._message_fetch([], thread=channel)["messages"]
        self.assertEqual(on_web.ids, [sent["id"]])
        self.assertEqual((on_web.author_id, on_web.attachment_ids.name), (self.tester.partner_id, "worksheet.pdf"))
        attachment = sent["attachments"][0]["id"]
        self.assertEqual(self.on_phone("GET", f"/attachments/{attachment}").content, b"%PDF-1.7 worksheet")

        reply = channel.with_user(self.member).message_post(body="Got it", message_type="comment")
        after = self.answered(self.on_phone("GET", f"{path}?after={sent['id']}"))["messages"]
        self.assertEqual(
            [(message["id"], message["text"], message["mine"]) for message in after], [(reply.id, "Got it", False)]
        )
        page = self.answered(self.on_phone("GET", f"{path}?before={reply.id}"))["messages"]
        self.assertEqual([message["id"] for message in page], [sent["id"]])

    def test_a_message_without_text_or_files_is_refused(self):
        path = f"/conversations/{self.group()['id']}/messages"

        self.assertApiRefused(INVALID_REQUEST, self.on_phone("POST", path, {"text": "  "}))

    def test_a_file_over_its_limit_is_refused_before_anything_is_stored(self):
        channel = self.channel(self.group())
        file = {"name": "photo.jpg", "mimetype": "image/jpeg", "data": base64.b64encode(b"x" * 64).decode()}

        with patch(f"{MESSAGES}.FILE_MAX_BYTES", 32):
            refused = self.on_phone("POST", f"/conversations/{channel.id}/messages", {"files": [file]})
        with patch(f"{MESSAGES}.REQUEST_FILES_MAX_BYTES", 100):
            together = self.on_phone("POST", f"/conversations/{channel.id}/messages", {"files": [file, file]})

        self.assertApiRefused(TOO_LARGE, refused)
        self.assertApiRefused(TOO_LARGE, together)
        self.assertFalse(
            self.env[MODEL_MAIL_MESSAGE].search(
                [("model", "=", MODEL_DISCUSS_CHANNEL), ("res_id", "=", channel.id), ("message_type", "=", "comment")]
            )
        )

    def test_marking_seen_reads_the_conversation_on_the_web_as_well(self):
        channel = self.channel(self.group())
        message = channel.with_user(self.member).message_post(body="Results are in", message_type="comment")

        seen = self.on_phone("POST", f"/conversations/{channel.id}/seen", {"message_id": message.id})

        self.assertEqual(seen.status_code, 204, seen.text)
        self.assertEqual(channel.with_user(self.tester).self_member_id.seen_message_id, message)
        self.assertEqual(self.answered(self.on_phone("GET", "/conversations"))["conversations"][0]["unread"], 0)

    # Pushes

    def test_a_message_is_pushed_at_once_to_members_except_its_author_and_those_who_muted_it(self):
        channel = self.channel(self.group())
        muted = channel.with_user(self.colleague)
        muted.self_member_id.mute_until_dt = "9999-12-31 23:59:59"
        triggers = self.env[MODEL_IR_CRON_TRIGGER].search_count([])

        sent = self.answered(
            self.on_phone("POST", f"/conversations/{channel.id}/messages", {"text": "Lead is over the limit"})
        )

        message = self.message(sent)
        self.assertEqual(self.pushed(message), self.member)
        self.assertGreater(self.env[MODEL_IR_CRON_TRIGGER].search_count([]), triggers)
        delivery = self.env[MODEL_PUSH_DELIVERY].search([("message_id", "=", message.id)])
        title, body, data = delivery.with_user(self.member)._push_message()
        self.assertEqual((title, body), ("Pesticides morning shift", self.tester.name))
        self.assertEqual(data, {"event": "message", "model": MODEL_DISCUSS_CHANNEL, "id": str(channel.id)})
        self.assertNotIn("Lead", f"{title} {body} {data}")

    def test_muting_on_the_phone_stops_pushes_until_unmuted(self):
        channel = self.channel(self.group())
        member_key = self.signed_in_key(self.member, "member-phone", name="Galaxy", platform="android")
        path = f"/conversations/{channel.id}/mute"

        self.assertTrue(self.answered(self.on_phone("PUT", path, {"muted": True}, key=member_key))["muted"])
        first = channel.with_user(self.colleague).message_post(body="Muted", message_type="comment")
        self.assertFalse(self.answered(self.on_phone("PUT", path, {"muted": False}, key=member_key))["muted"])
        second = channel.with_user(self.colleague).message_post(body="Unmuted", message_type="comment")

        self.assertEqual(self.pushed(first), self.tester)
        self.assertEqual(self.pushed(second), self.tester | self.member)

    def test_a_mention_reaches_a_member_who_muted_the_conversation(self):
        channel = self.channel(self.group())
        channel.with_user(self.colleague).self_member_id.mute_until_dt = "9999-12-31 23:59:59"

        sent = self.answered(
            self.on_phone(
                "POST",
                f"/conversations/{channel.id}/messages",
                {"text": "@Colleague check", "mentions": [self.colleague.id]},
            )
        )

        message = self.message(sent)
        self.assertEqual(self.pushed(message), self.member | self.colleague)
        self.assertEqual(message.partner_ids, self.colleague.partner_id)

    def test_a_mention_notifies_on_each_channel_the_person_keeps_on(self):
        channel = self.channel(self.group())
        event = self.env[MODEL_MAIL_MESSAGE_SUBTYPE]._event(EVENT_MESSAGE_MENTION)
        self.colleague.write({"notification_type": "inbox", "email": "colleague@example.com"})
        preferences = self.env[MODEL_NOTIFICATION_PREFERENCE].with_user(self.colleague)
        preferences.set_own(event, CHANNEL_EMAIL, True)
        preferences.set_own(event, CHANNEL_PUSH, False)
        channel.with_user(self.colleague).self_member_id.mute_until_dt = "9999-12-31 23:59:59"

        sent = self.answered(
            self.on_phone(
                "POST",
                f"/conversations/{channel.id}/messages",
                {"text": "Please check", "mentions": [self.colleague.id]},
            )
        )

        message = self.message(sent)
        notification = self.env[MODEL_MAIL_NOTIFICATION].search(
            [("mail_message_id", "=", message.id), ("res_partner_id", "=", self.colleague.partner_id.id)]
        )
        self.assertEqual(notification.notification_type, "inbox")
        self.assertTrue(notification.mail_mail_id)
        self.assertNotIn(self.colleague, self.pushed(message))

    def test_a_message_from_the_web_is_pushed_to_the_phone(self):
        channel = self.channel(self.group())

        message = channel.with_user(self.member).message_post(body="From the web", message_type="comment")

        self.assertEqual(self.pushed(message), self.tester | self.colleague)
        self.assertEqual(self.tokens[self.tester].user_id, self.tester)

    def test_a_member_added_on_the_web_must_be_of_the_laboratory(self):
        channel = self.channel(self.group())

        channel._add_members(users=self.outsider)

        self.assertIn(self.outsider.partner_id, channel.channel_member_ids.partner_id)
        with self.assertRaises(ValidationError):
            self.env[MODEL_DISCUSS_CHANNEL].create(
                {
                    "name": "With a customer",
                    "channel_type": "group",
                    "channel_member_ids": [Command.create({"partner_id": self.customer.partner_id.id})],
                }
            )

    def test_a_message_of_a_public_channel_is_pushed_only_to_the_people_it_mentions(self):
        channel = self.env[MODEL_DISCUSS_CHANNEL].create({"name": "Laboratory news", "channel_type": "channel"})
        channel._add_members(users=self.tester | self.member | self.colleague)

        message = channel.with_user(self.tester).message_post(
            body="Fire drill at 10", message_type="comment", partner_ids=self.colleague.partner_id.ids
        )

        self.assertEqual(self.pushed(message), self.colleague)
