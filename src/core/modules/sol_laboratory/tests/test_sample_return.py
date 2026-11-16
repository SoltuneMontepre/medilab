from datetime import timedelta

from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import tagged

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_HANDOVER_RECORD,
    MODEL_PERSON,
    MODEL_SAMPLE_RETURN,
    MODEL_SCHEDULED_JOB,
    MODEL_TASK,
)
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_RETENTION_CODE


@tagged("post_install", "-at_install")
class TestSampleReturn(RequestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.staff = cls.env.ref("sol_laboratory.person_administrator")
        cls.today = cls.sample._company_today()

    def hand_over(self, signed=True, **line):
        """A handover record of the sample, signed unless told otherwise, with what the line says was handed over."""
        record = self.env[MODEL_HANDOVER_RECORD].create(
            {
                "request_id": self.request.id,
                "handed_over_by_name": "Tran Van Khach",
                "received_by_id": self.staff.id,
                "sample_ids": [
                    Command.create({"sample_id": self.sample.id, "quantity": "2 L", "condition": "good", **line})
                ],
            }
        )
        if signed:
            record.sudo().write({"status": "signed"})
        return record

    def give_back(self, kind="extras", sample=None):
        return (
            self.env[MODEL_SAMPLE_RETURN]
            .with_user(self.staff.user_id)
            .create(
                {
                    "sample_id": (sample or self.sample).id,
                    "kind": kind,
                    "description": "300 mL of bottled water the tests did not use",
                    "returned_to_name": "Tran Van Khach",
                }
            )
        )

    def test_a_return_records_what_when_by_whom_and_to_whom(self):
        self.hand_over(excess_material="300 mL more than required")

        returned = self.give_back()

        self.assertEqual(returned.description, "300 mL of bottled water the tests did not use")
        self.assertTrue(returned.returned_at)
        self.assertEqual(returned.returned_by_id, self.staff)
        self.assertEqual(returned.returned_to_name, "Tran Van Khach")
        self.assertEqual(self.sample.return_ids, returned)

    def test_returning_excess_material_leaves_the_sample_state_unchanged(self):
        self.hand_over(excess_material="300 mL more than required")
        self.sample.write({"status": "reported"})

        self.give_back()
        self.give_back()

        self.assertEqual(self.sample.status, "reported")
        self.assertEqual(len(self.sample.return_ids), 2)
        self.assertEqual(self.sample.returnable, "extras")

    def test_only_what_a_signed_record_lists_beyond_the_expected_samples_is_returned(self):
        self.hand_over()
        with self.assertRaises(UserError):
            self.give_back()
        self.hand_over(signed=False, excess_material="300 mL more than required")

        with self.assertRaises(UserError):
            self.give_back()
        self.assertFalse(self.sample.returnable)

    def test_a_retained_sample_cannot_be_returned_before_its_retention_ends(self):
        self.sample.write({"status": "retained", "retained_until": self.today + timedelta(days=1)})

        self.assertFalse(self.sample.returnable)
        with self.assertRaises(UserError):
            self.give_back("retained")
        self.assertEqual(self.sample.status, "retained")

    def test_a_retained_sample_returned_after_its_retention_ends_as_returned(self):
        self.sample.write({"status": "retained", "retained_until": self.today})
        self.env[MODEL_SCHEDULED_JOB]._run_key("sample.retention.reminders")
        reminder = self.env[MODEL_TASK].search(
            [
                ("type_id.code", "=", SAMPLE_RETENTION_CODE),
                ("document_model", "=", self.sample._name),
                ("document_id", "=", self.sample.id),
            ]
        )

        self.assertEqual(self.sample.returnable, "retained")
        self.give_back("retained")

        self.assertEqual(self.sample.status, "returned")
        self.assertEqual(reminder.status, "cancelled")
        with self.assertRaises(UserError):
            self.sample.action_dispose("Pour into the drain.")
        with self.assertRaises(UserError):
            self.sample.write({"status": "retained"})

    def test_only_a_person_with_the_permission_records_a_return(self):
        self.hand_over(excess_material="300 mL more than required")
        tester = self.env[MODEL_PERSON].create({"name": "Le Van Cuong", "login": "return.tester"})

        with self.assertRaises(AccessError):
            self.env[MODEL_SAMPLE_RETURN].with_user(tester.user_id).create(
                {"sample_id": self.sample.id, "description": "300 mL", "returned_to_name": "Tran Van Khach"}
            )
        self.assertFalse(self.sample.return_ids)
