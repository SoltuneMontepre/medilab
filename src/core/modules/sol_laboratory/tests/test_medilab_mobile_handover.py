import base64

from odoo import fields
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from .mobile_phones import PhoneCalls, phone_person
from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.laboratory_files import INVALID_REQUEST, NOT_FOUND, PERMISSION_DENIED
from odoo.addons.sol_laboratory.constants.medilab_mobile import ACTION_REFUSED, SIGNATURE_MAX_BYTES, TOO_LARGE
from odoo.addons.sol_laboratory.constants.models import MODEL_HANDOVER_RECORD, MODEL_LABORATORY_DEVICE

# The customer's handwritten signature as the phone draws it: a PNG.
SIGNATURE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
# What sample delivery staff may do with handover records, as the demo staff may.
STAFF_PERMISSIONS = (
    "handover_record_read_all",
    "handover_record_edit_all",
    "handover_record_sample_read_all",
    "test_request_read_all",
    "sample_read_all",
    "customer_read_all",
)
# A person who reads handover records and may not have them signed.
READER_PERMISSIONS = ("handover_record_read_all", "handover_record_sample_read_all")


def signature_body(signature=SIGNATURE):
    return {"signature": base64.b64encode(signature).decode(), "confirmed": True}


@tagged("post_install", "-at_install")
class TestMedilabMobileHandover(PhoneCalls, RequestCase):
    """The customer's signature on a handover record on Medilab Mobile: sample delivery staff open a draft record, the
    customer reads the samples on it and signs on the phone, and the phone is recorded."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer.email = "reception@anphu.example"
        cls.staff = phone_person(cls.env, "Le Thi Lan", "lan.handover", None, STAFF_PERMISSIONS)
        cls.reader = phone_person(cls.env, "Pham Van Doc", "doc.handover", None, READER_PERMISSIONS)
        cls.tester = phone_person(cls.env, "Nguyen Van An", "an.handover", cls.department, ("sample_read_all",))
        cls.record = cls.env[MODEL_HANDOVER_RECORD].create(
            {
                "request_id": cls.request.id,
                "handed_over_at": fields.Datetime.now(),
                "handed_over_by_name": "Tran Van Khach",
                "received_by_id": cls.staff.id,
                "sample_ids": [
                    Command.create(
                        {
                            "sample_id": cls.sample.id,
                            "quantity": "2 bottles of 1 L",
                            "excess_material": "300 mL more than required",
                            "condition": "good",
                        }
                    )
                ],
            }
        )

    def sign(self, person, body=None):
        return self.on_phone(person, "POST", f"/handover-records/{self.record.id}/sign", body or signature_body())

    def phone_of(self, person):
        self.on_phone(person, "GET", "/me")
        return self.env[MODEL_LABORATORY_DEVICE].search([("client_uid", "=", f"phone-{person.id}")])

    def test_staff_list_the_draft_record_and_read_its_samples(self):
        drafts = self.answered(self.on_phone(self.staff, "GET", "/handover-records?status=draft"))
        signed = self.answered(self.on_phone(self.staff, "GET", "/handover-records?status=signed"))
        record = self.answered(self.on_phone(self.staff, "GET", f"/handover-records/{self.record.id}"))

        self.assertIn(self.record.id, [listed["id"] for listed in drafts["records"]])
        self.assertNotIn(self.record.id, [listed["id"] for listed in signed["records"]])
        self.assertEqual((record["status"], record["handed_over_by"]), ("draft", "Tran Van Khach"))
        self.assertTrue(record["can_sign"])
        [sample] = record["samples"]
        self.assertEqual(sample["code"], self.sample.code)
        self.assertEqual(
            (sample["quantity"], sample["excess_material"]), ("2 bottles of 1 L", "300 mL more than required")
        )

    def test_a_record_signed_on_the_phone_records_the_phone_emails_the_pdf_and_cannot_change(self):
        signed = self.answered(self.sign(self.staff))

        phone = self.phone_of(self.staff)
        self.assertEqual(self.record.status, "signed")
        self.assertEqual(self.record.signed_device_id, phone)
        self.assertEqual(bytes(self.record.signature_attachment_id.raw), SIGNATURE)
        self.assertEqual((signed["status"], signed["signed_device"], signed["can_sign"]), ("signed", "Pixel 8", False))
        mail = self.env["mail.mail"].search([("model", "=", MODEL_HANDOVER_RECORD), ("res_id", "=", self.record.id)])
        self.assertEqual(mail.email_to, "reception@anphu.example")
        self.assertEqual(mail.attachment_ids, self.record.attachment_id)
        with self.assertRaises(UserError):
            self.record.handed_over_by_name = "Someone else"

    def test_a_signature_sent_again_from_the_same_phone_answers_the_signed_record(self):
        self.answered(self.sign(self.staff))
        signature = self.record.signature_attachment_id

        again = self.answered(self.sign(self.staff, signature_body(SIGNATURE + b"signed again")))

        self.assertEqual(again["status"], "signed")
        self.assertEqual(self.record.signature_attachment_id, signature)

    def test_another_phone_cannot_sign_a_signed_record(self):
        self.answered(self.sign(self.staff))
        other = self.signed_in_key(self.staff.user_id, "another-phone", name="Galaxy A55", platform="android")

        refused = self.api("POST", f"/handover-records/{self.record.id}/sign", signature_body(), key=other)

        self.assertApiRefused(ACTION_REFUSED, refused)
        self.assertEqual(self.record.signed_device_id, self.phone_of(self.staff))

    def test_signing_needs_a_confirmed_png_of_at_most_one_mib(self):
        unconfirmed = self.sign(self.staff, {"signature": signature_body()["signature"]})
        not_png = self.sign(self.staff, signature_body(b"GIF89a not a png"))
        too_large = self.sign(self.staff, signature_body(SIGNATURE + b"\0" * SIGNATURE_MAX_BYTES))

        self.assertApiRefused(INVALID_REQUEST, unconfirmed)
        self.assertApiRefused(INVALID_REQUEST, not_png)
        self.assertApiRefused(TOO_LARGE, too_large)
        self.assertEqual(self.record.status, "draft")

    def test_a_person_who_may_not_edit_the_record_cannot_have_it_signed(self):
        record = self.answered(self.on_phone(self.reader, "GET", f"/handover-records/{self.record.id}"))
        refused = self.sign(self.reader)

        self.assertFalse(record["can_sign"])
        self.assertApiRefused(PERMISSION_DENIED, refused)
        self.assertEqual(self.record.status, "draft")

    def test_a_person_without_handover_records_sees_none(self):
        me = self.answered(self.on_phone(self.tester, "GET", "/me"))
        staff = self.answered(self.on_phone(self.staff, "GET", "/me"))

        self.assertFalse(me["can"]["read_handover_records"])
        self.assertTrue(staff["can"]["read_handover_records"])
        self.assertApiRefused(NOT_FOUND, self.on_phone(self.tester, "GET", f"/handover-records/{self.record.id}"))
