from odoo import fields
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import new_test_user, tagged

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import MODEL_HANDOVER_RECORD, MODEL_MOBILE_DEVICE

EDITOR_PERMISSIONS = (
    "handover_record_read_all",
    "handover_record_edit_all",
    "handover_record_sample_read_all",
    "test_request_read_all",
    "sample_read_all",
    "customer_read_all",
)


@tagged("post_install", "-at_install")
class TestHandoverRecord(RequestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer.email = "reception@anphu.example"
        cls.record = cls.env[MODEL_HANDOVER_RECORD].create(
            {
                "request_id": cls.request.id,
                "handed_over_at": fields.Datetime.now(),
                "handed_over_by_name": "Tran Van Khach",
                "received_by_id": cls.env.ref("sol_laboratory.person_administrator").id,
                "sample_ids": [
                    Command.create({"sample_id": cls.sample.id, "quantity": "2 bottles of 1 L", "condition": "good"})
                ],
            }
        )
        cls.device = cls.env[MODEL_MOBILE_DEVICE].create(
            {"user_id": cls.env.ref("base.user_admin").id, "token": "handover-phone", "platform": "android"}
        )
        cls.editor = new_test_user(
            cls.env,
            login="handover.editor",
            groups=",".join(
                ["base.group_user", *(f"sol_laboratory.group_permission_{name}" for name in EDITOR_PERMISSIONS)]
            ),
        )

    def test_signing_stores_the_signature_and_device_and_emails_the_pdf(self):
        self.record.action_sign(b"signature-bytes", device_id=self.device.id)

        self.assertEqual(self.record.status, "signed")
        self.assertEqual(bytes(self.record.signature_attachment_id.raw), b"signature-bytes")
        self.assertTrue(self.record.signed_at)
        self.assertEqual(self.record.signed_device_id, self.device)
        self.assertTrue(self.record.attachment_id.raw)
        mail = self.env["mail.mail"].search([("model", "=", MODEL_HANDOVER_RECORD), ("res_id", "=", self.record.id)])
        self.assertEqual(mail.email_to, "reception@anphu.example")
        self.assertEqual(mail.attachment_ids, self.record.attachment_id)
        self.assertEqual(self.record.sent_at, self.record.signed_at)

    def test_a_signed_record_cannot_be_edited(self):
        self.record.action_sign(b"signature-bytes")

        with self.assertRaises(UserError):
            self.record.write({"handed_over_by_name": "Someone else"})
        with self.assertRaises(UserError):
            self.record.sample_ids.write({"quantity": "1 bottle"})
        with self.assertRaises(UserError):
            self.record.action_sign(b"another-signature")

    def test_only_signing_marks_a_record_signed(self):
        record = self.record.with_user(self.editor)

        with self.assertRaises(UserError):
            record.write({"status": "signed"})
        self.assertEqual(record.status, "draft")
        record.action_sign(b"signature-bytes")
        self.assertEqual(record.status, "signed")

    def test_the_files_of_a_signed_record_cannot_be_replaced(self):
        self.record.action_sign(b"signature-bytes")

        for attachment in self.record.attachment_id | self.record.signature_attachment_id:
            with self.subTest(attachment=attachment.name), self.assertRaises(UserError):
                attachment.with_user(self.editor).write({"raw": b"forged"})
