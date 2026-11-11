from odoo import fields
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DEPARTMENT,
    MODEL_PARAMETER_METHOD,
    MODEL_PERMISSION,
    MODEL_PERSON,
    MODEL_ROLE,
    MODEL_SAMPLE_HANDOVER,
    MODEL_SAMPLE_TEST,
    MODEL_SUBCONTRACTOR,
    MODEL_TASK,
)
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_COLLECTION_CODE, SAMPLE_TEST_CODE
from odoo.addons.sol_laboratory.services.model_lookup import reference_as
from odoo.addons.sol_laboratory.services.record_id import persisted_id, persisted_ids


@tagged("post_install", "-at_install")
class TestSampleReception(RequestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.staff = cls.env.ref("sol_laboratory.person_administrator")
        permission = "sol_laboratory.permission_{}"
        cls.scanner_role = cls.env[MODEL_ROLE].create(
            {
                "code": "scanner",
                "name": "Scanner",
                "permission_ids": [
                    Command.set(
                        [
                            persisted_id(cls.env.ref(permission.format(name)))
                            for name in (
                                "sample_read_all",
                                "sample_handover_read_own_department",
                                "sample_handover_edit_own_department",
                            )
                        ]
                    )
                ],
            }
        )

    def department_person(self, name, login, department):
        return self.env[MODEL_PERSON].create(
            {
                "name": name,
                "login": login,
                "department_id": department.id,
                "role_ids": [Command.set(persisted_ids(self.scanner_role))],
            }
        )

    def receive(self, *args, **kwargs):
        sample = self.sample.with_user(self.staff.user_id)
        sample.action_receive(*args, **kwargs)
        return sample

    def test_good_receipt_creates_a_testing_task_for_each_in_house_test(self):
        subcontractor_id, _name = self.env[MODEL_SUBCONTRACTOR].name_create("Outside Lab")
        outside = self.create_parameter("Arsenic (As)", self.group)
        way = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": outside.id,
                "method_id": self.method.id,
                "subcontractor_id": subcontractor_id,
            }
        )
        self.offer(outside, self.sample_type, way)
        self.env[MODEL_SAMPLE_TEST].create({"sample_id": self.sample.id, "parameter_id": outside.id})

        sample = self.receive("2 bottles of 1 L", "good", storage_location="Fridge 2, shelf B")

        self.assertEqual(sample.status, "received")
        self.assertEqual(sample.received_quantity, "2 bottles of 1 L")
        self.assertEqual(sample.storage_location, "Fridge 2, shelf B")
        self.assertTrue(sample.received_at)
        self.assertEqual(sample.received_by_id, self.staff)
        in_house = sample.test_ids.filtered(lambda test: test.parameter_id == self.parameter)
        tasks = self.env[MODEL_TASK].search(
            [
                ("type_id.code", "=", SAMPLE_TEST_CODE),
                ("document_model", "=", MODEL_SAMPLE_TEST),
                ("document_id", "in", sample.test_ids.ids),
            ]
        )
        self.assertEqual(tasks.mapped("document_id"), [in_house.id])
        self.assertEqual(tasks.status, "open")
        self.assertEqual(tasks.department_id, self.department)
        self.assertEqual(sample.handover_ids.department_id, self.department)

    def test_damaged_receipt_rejects_the_sample_and_creates_no_testing_task(self):
        sample = self.receive("1 bottle", "damaged", condition_note="The bottle cracked and the sample leaked.")

        self.assertEqual(sample.status, "rejected")
        self.assertEqual(sample.condition_note, "The bottle cracked and the sample leaked.")
        self.assertFalse(
            self.env[MODEL_TASK].search(
                [
                    ("type_id.code", "=", SAMPLE_TEST_CODE),
                    ("document_model", "=", MODEL_SAMPLE_TEST),
                    ("document_id", "in", sample.test_ids.ids),
                ]
            )
        )
        self.assertFalse(sample.handover_ids)

    def test_receiving_the_first_sample_moves_the_request_to_sample_received(self):
        self.request.action_confirm()

        self.receive("2 bottles of 1 L", "good")

        self.assertEqual(self.request.status, "sample_received")

    def test_rejecting_a_sample_without_its_reason_is_refused(self):
        with self.assertRaises(UserError):
            self.receive("1 bottle", "damaged")

    def test_insufficient_receipt_holds_the_sample_and_tells_the_head(self):
        head = self.env[MODEL_PERSON].create(
            {"name": "Le Thi Hoa", "login": "hoa.le", "department_id": self.department.id}
        )
        head.user_id.notification_type = "inbox"
        self.department.manager_id = head.employee_id
        other = self.env[MODEL_DEPARTMENT].create({"name": "Reception"})
        other.manager_id = self.env[MODEL_PERSON].create({"name": "Do Van Khac", "login": "khac.do"}).employee_id

        sample = self.receive("50 mL", "insufficient", condition_note="Below the minimum amount.")

        self.assertEqual(sample.status, "on_hold")
        self.assertFalse(
            self.env[MODEL_TASK].search(
                [("type_id.code", "=", SAMPLE_TEST_CODE), ("document_id", "in", sample.test_ids.ids)]
            )
        )
        message = self.env["mail.message"].search([("model", "=", sample._name), ("res_id", "=", sample.id)])
        self.assertEqual(message.subtype_id, self.env.ref("sol_laboratory.event_sample_insufficient"))
        self.assertEqual(message.notification_ids.res_partner_id, head.user_id.partner_id)

    def test_the_head_of_department_asks_to_collect_again_and_one_task_is_created(self):
        head = self.head_of(self.department)
        sample = self.receive("50 mL", "insufficient")

        with self.assertRaises(UserError):
            sample.action_request_recollection()
        sample.with_user(head.user_id).action_request_recollection()

        self.assertEqual(sample.recollection_requested_by_id, head)
        self.assertTrue(sample.recollection_requested_at)
        tasks = self.env[MODEL_TASK].search(
            [("type_id.code", "=", SAMPLE_COLLECTION_CODE), ("document_id", "=", sample.id)]
        )
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks.assignee_id, sample.received_by_id)
        with self.assertRaises(UserError):
            sample.with_user(head.user_id).action_request_recollection()

    def test_more_sample_puts_it_back_to_received_with_its_testing_tasks(self):
        sample = self.receive("50 mL", "insufficient")

        sample.action_receive_more("1 L")

        self.assertEqual(sample.status, "received")
        self.assertTrue(
            self.env[MODEL_TASK].search(
                [("type_id.code", "=", SAMPLE_TEST_CODE), ("document_id", "in", sample.test_ids.ids)]
            )
        )

    def test_two_handovers_show_which_department_received_the_sample(self):
        microbiology = self.env[MODEL_DEPARTMENT].create({"name": "Microbiology"})
        parameter = self.create_parameter("Coliforms", self.group)
        way = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": parameter.id,
                "method_id": self.method.id,
                "department_id": microbiology.id,
            }
        )
        self.offer(parameter, self.sample_type, way)
        self.env[MODEL_SAMPLE_TEST].create({"sample_id": self.sample.id, "parameter_id": parameter.id})
        chemist = self.department_person("Nguyen Van An", "an.scan", self.department)
        sample = self.receive("1 L", "good")

        self.env[MODEL_SAMPLE_HANDOVER].with_user(chemist.user_id).receive_by_label(sample.code)

        self.assertEqual(set(sample.handover_ids.department_id.ids), {self.department.id, microbiology.id})
        received = sample.handover_ids.filtered("received_at")
        self.assertEqual(received.department_id, self.department)
        self.assertEqual(len(sample.handover_ids), 2)

    def test_only_the_department_can_scan_the_sample_label(self):
        sample = self.receive("1 L", "good")
        insider = self.department_person("Nguyen Van An", "an.scan", self.department)
        microbiology = self.env[MODEL_DEPARTMENT].create({"name": "Microbiology"})
        outsider = self.department_person("Tran Thi Binh", "binh.scan", microbiology)

        handover = self.env[MODEL_SAMPLE_HANDOVER].with_user(insider.user_id).receive_by_label(sample.code)

        self.assertEqual(handover.received_by_id, insider)
        self.assertEqual(handover.department_id, self.department)
        with self.assertRaises(UserError):
            self.env[MODEL_SAMPLE_HANDOVER].with_user(outsider.user_id).receive_by_label(sample.code)

    def test_a_department_receipt_is_recorded_only_by_scanning_the_label(self):
        sample = self.receive("1 L", "good")
        microbiology = self.env[MODEL_DEPARTMENT].create({"name": "Microbiology"})
        clerk = self.env[MODEL_PERSON].create(
            {
                "name": "Tran Thi Binh",
                "login": "binh.clerk",
                "department_id": microbiology.id,
                "permission_ids": [
                    Command.set(
                        [
                            persisted_id(reference_as(self.env[MODEL_PERMISSION], f"sol_laboratory.permission_{name}"))
                            for name in ("sample_read_all", "sample_handover_read_all", "sample_handover_edit_all")
                        ]
                    )
                ],
            }
        )
        handover = sample.handover_ids.with_user(clerk.user_id)

        with self.assertRaises(UserError):
            handover.write({"received_at": fields.Datetime.now(), "received_by_id": clerk.id})
        insider = self.department_person("Nguyen Van An", "an.scan", self.department)
        self.env[MODEL_SAMPLE_HANDOVER].with_user(insider.user_id).receive_by_label(sample.code)
        with self.assertRaises(UserError):
            handover.write({"department_id": microbiology.id})
        self.assertEqual((handover.department_id, handover.received_by_id), (self.department, insider))
