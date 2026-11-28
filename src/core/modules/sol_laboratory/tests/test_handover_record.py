from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import Form, new_test_user, tagged
from odoo.tools import mute_logger

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import MODEL_EXPECTED_SAMPLING, MODEL_HANDOVER_RECORD

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
        cls.record = cls.handover_for(cls.sample)
        cls.editor = new_test_user(
            cls.env,
            login="handover.editor",
            groups=",".join(
                ["base.group_user", *(f"sol_laboratory.group_permission_{name}" for name in EDITOR_PERMISSIONS)]
            ),
        )

    def test_signing_stores_the_signature_and_emails_the_pdf(self):
        self.record.action_sign(b"signature-bytes")

        self.assertEqual(self.record.status, "signed")
        self.assertEqual(bytes(self.record.signature_attachment_id.raw), b"signature-bytes")
        self.assertTrue(self.record.signed_at)
        # Only Medilab Mobile's route records the phone a record was signed on.
        self.assertFalse(self.record.signed_device_id)
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

    def test_the_record_lists_the_actual_samples_against_the_expected_ones(self):
        self.env[MODEL_EXPECTED_SAMPLING].create(
            {"sample_id": self.sample.id, "objects": 2, "group_number": 1, "container_type": "PET bottle"}
        )
        line = self.record.sample_ids

        self.assertEqual((line.expected_count, line.actual_count), (2, 2))
        line.actual_count = 3
        self.assertEqual((line.extra_count, line.missing_count), (1, 0))
        line.actual_count = 1
        self.assertEqual((line.extra_count, line.missing_count), (0, 1))
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            line.actual_count = 0
            line.flush_recordset()

    def test_extra_samples_and_excess_material_add_no_test_and_stay_with_the_sample(self):
        self.env[MODEL_EXPECTED_SAMPLING].create({"sample_id": self.sample.id, "objects": 1, "group_number": 1})
        tests = self.sample.test_ids
        self.record.sample_ids.write({"actual_count": 2, "excess_material": "300 mL more than required"})

        self.record.action_sign(b"signature-bytes")

        self.assertEqual(self.record.sample_ids.extra_count, 1)
        self.assertEqual(self.sample.test_ids, tests)
        self.assertTrue(self.sample._extras_kept())
        self.assertEqual(self.sample.returnable, "extras")

    def test_a_sample_handed_over_short_waits_for_another_collection(self):
        self.env[MODEL_EXPECTED_SAMPLING].create({"sample_id": self.sample.id, "objects": 2, "group_number": 1})
        self.record.sample_ids.actual_count = 1
        self.record.action_sign(b"signature-bytes")

        self.assertEqual(self.record.sample_ids.missing_count, 1)
        self.assertEqual(self.sample.status, "expected")
        self.assertFalse(self.sample._extras_kept())
        later = self.env[MODEL_HANDOVER_RECORD].create(
            {
                "request_id": self.request.id,
                "handed_over_by_name": "Tran Van Khach",
                "received_by_id": self.record.received_by_id.id,
                "sample_ids": [
                    Command.create(
                        {"sample_id": self.sample.id, "actual_count": 1, "quantity": "1 bottle", "condition": "good"}
                    )
                ],
            }
        )
        later.action_sign(b"signature-bytes")
        self.assertEqual(self.sample.handover_line_ids.mapped("actual_count"), [1, 1])

    def test_choosing_the_request_lists_its_samples_still_to_be_handed_over(self):
        form = Form(self.env[MODEL_HANDOVER_RECORD])
        form.request_id = self.request
        self.assertEqual(len(form.sample_ids), 0)

        self.env[MODEL_EXPECTED_SAMPLING].create({"sample_id": self.sample.id, "objects": 2, "group_number": 1})
        self.record.sample_ids.actual_count = 1
        form = Form(self.env[MODEL_HANDOVER_RECORD])
        form.request_id = self.request
        self.assertEqual(len(form.sample_ids), 1)
        with form.sample_ids.edit(0) as line:
            self.assertEqual(line.sample_id, self.sample)
            line.quantity = "1 bottle"
            line.condition = "good"

    def test_the_files_of_a_signed_record_cannot_be_replaced(self):
        self.record.action_sign(b"signature-bytes")

        for attachment in self.record.attachment_id | self.record.signature_attachment_id:
            with self.subTest(attachment=attachment.name), self.assertRaises(UserError):
                attachment.with_user(self.editor).write({"raw": b"forged"})
