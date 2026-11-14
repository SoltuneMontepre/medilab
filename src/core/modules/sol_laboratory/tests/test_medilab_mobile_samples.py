from urllib.parse import quote

from odoo.fields import Command, Domain
from odoo.tests import tagged

from .laboratory_api_case import LaboratoryApiCase
from .laboratory_files_case import PASSWORD
from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.laboratory_files import INVALID_REQUEST, NOT_FOUND
from odoo.addons.sol_laboratory.constants.medilab_mobile import ACTION_REFUSED, ALREADY_CLAIMED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DEPARTMENT,
    MODEL_PARAMETER_AUTHORIZATION,
    MODEL_PARAMETER_METHOD,
    MODEL_PERMISSION,
    MODEL_PERSON,
    MODEL_SAMPLE_TEST,
    MODEL_TASK,
)
from odoo.addons.sol_laboratory.services.model_lookup import reference_as
from odoo.addons.sol_laboratory.services.record_id import persisted_id

# What a person of a department that tests samples may do with them, as the demo tester may.
DEPARTMENT_PERMISSIONS = (
    "sample_read_all",
    "sample_handover_read_own_department",
    "sample_handover_edit_own_department",
)


@tagged("post_install", "-at_install")
class TestMedilabMobileSamples(LaboratoryApiCase, RequestCase):
    """Scanning a sample's label on Medilab Mobile: a sample tested for lead by Analytical chemistry and for coliforms
    by Microbiology, received by the laboratory and handed over to both, and scanned by two chemists, a microbiologist,
    a person of a department it was not handed over to and a receptionist who reads every test request."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.microbiology = cls.env[MODEL_DEPARTMENT].create({"name": "Microbiology"})
        coliforms = cls.create_parameter("Coliforms", cls.group)
        way = cls.env[MODEL_PARAMETER_METHOD].create(
            {"parameter_id": coliforms.id, "method_id": cls.method.id, "department_id": cls.microbiology.id}
        )
        cls.offer(coliforms, cls.sample_type, way)
        cls.env[MODEL_SAMPLE_TEST].create({"sample_id": cls.sample.id, "parameter_id": coliforms.id})
        staff = cls.env.ref("sol_laboratory.person_administrator")
        cls.sample.with_user(staff.user_id).action_receive("2 bottles of 1 L", "good")
        cls.chemist = cls.department_person("Nguyen Van An", "an.scan", cls.department)
        cls.second_chemist = cls.department_person("Pham Thi Dung", "dung.scan", cls.department)
        cls.microbiologist = cls.department_person("Tran Thi Binh", "binh.scan", cls.microbiology)
        # The Lab Head authorizes the chemists for lead and the microbiologist for coliforms.
        cls.env[MODEL_PARAMETER_AUTHORIZATION].create(
            [
                {"person_id": person.id, "parameter_id": parameter.id}
                for person, parameter in (
                    (cls.chemist, cls.parameter),
                    (cls.second_chemist, cls.parameter),
                    (cls.microbiologist, coliforms),
                )
            ]
        )
        physics = cls.env[MODEL_DEPARTMENT].create({"name": "Physics"})
        cls.physicist = cls.department_person("Le Van Cuong", "cuong.scan", physics)
        cls.receptionist = cls.department_person(
            "Vo Thi Hanh", "hanh.scan", None, extra=("test_request_read_all", "customer_read_all")
        )
        testing = cls.env[MODEL_TASK].search(
            cls.env[MODEL_TASK]._testing_domain() & Domain("document_id", "in", cls.sample.test_ids.ids)
        )
        cls.lead_task = testing.filtered(lambda task: task.department_id == cls.department)
        cls.coliforms_task = testing.filtered(lambda task: task.department_id == cls.microbiology)

    @classmethod
    def department_person(cls, name, login, department, extra=()):
        person = cls.env[MODEL_PERSON].create(
            {
                "name": name,
                "login": login,
                "department_id": department.id if department else False,
                "permission_ids": [
                    Command.set(
                        [
                            persisted_id(reference_as(cls.env[MODEL_PERMISSION], f"sol_laboratory.permission_{code}"))
                            for code in (*DEPARTMENT_PERMISSIONS, *extra)
                        ]
                    )
                ],
            }
        )
        person.user_id.password = PASSWORD
        return person

    def setUp(self):
        super().setUp()
        self.keys = {}

    def on_phone(self, person, method, path, body=None):
        if person not in self.keys:
            self.keys[person] = self.signed_in_key(
                person.user_id, f"phone-{person.id}", name="Pixel 8", platform="android"
            )
        return self.api(method, path, body, key=self.keys[person])

    def answered(self, response) -> dict:
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def look_up(self, person, code=None):
        label = code or self.sample.code or ""
        return self.on_phone(person, "GET", f"/samples/lookup?code={quote(label)}")

    def handover_of(self, department):
        return self.sample.handover_ids.filtered(lambda handover: handover.department_id == department)

    # Looking up a label

    def test_a_tester_sees_the_sample_without_its_customer_and_only_their_department_tasks(self):
        sample = self.answered(self.look_up(self.chemist))

        self.assertEqual((sample["id"], sample["code"]), (self.sample.id, self.sample.code))
        self.assertIsNone(sample["customer"])
        self.assertIsNone(sample["customer_sample_name"])
        self.assertEqual(
            sample["handover"],
            {"department": self.department.name, "received_at": None, "received_by": "", "can_receive": True},
        )
        self.assertEqual([task["id"] for task in sample["tasks"]], self.lead_task.ids)
        microbiology = self.answered(self.look_up(self.microbiologist))
        self.assertEqual([task["id"] for task in microbiology["tasks"]], self.coliforms_task.ids)

    def test_a_person_who_reads_every_test_request_sees_the_customer(self):
        sample = self.answered(self.look_up(self.receptionist))

        self.assertEqual(sample["customer"], self.customer.display_name)
        self.assertEqual(sample["customer_sample_name"], "Lavie bottled water 1 L")
        self.assertIsNone(sample["handover"])
        self.assertEqual(sample["tasks"], [])

    def test_a_code_of_no_sample_or_of_one_the_person_may_not_read_is_not_found(self):
        outsider = self.department_person("Dang Van Duc", "duc.scan", self.department)
        outsider.permission_ids = [Command.clear()]

        self.assertApiRefused(NOT_FOUND, self.look_up(self.chemist, "PTN.0000.0000"))
        self.assertApiRefused(NOT_FOUND, self.look_up(outsider))
        self.assertApiRefused(NOT_FOUND, self.on_phone(outsider, "GET", f"/samples/{self.sample.id}"))
        self.assertEqual(
            self.answered(self.on_phone(self.chemist, "GET", f"/samples/{self.sample.id}"))["code"], self.sample.code
        )

    # Recording the receipt

    def test_only_a_person_who_may_edit_the_handover_is_offered_the_receipt(self):
        reader = self.department_person("Dang Van Duc", "duc.scan", self.department)
        reader.permission_ids = [
            Command.set(
                [
                    persisted_id(reference_as(self.env[MODEL_PERMISSION], f"sol_laboratory.permission_{code}"))
                    for code in ("sample_read_all", "sample_handover_read_own_department")
                ]
            )
        ]

        handover = self.answered(self.look_up(reader))["handover"]

        self.assertFalse(handover["can_receive"])
        self.assertApiRefused(NOT_FOUND, self.on_phone(reader, "POST", "/samples/receive", {"code": self.sample.code}))
        self.assertFalse(self.handover_of(self.department).received_at)

    def test_scanning_records_the_receipt_once_for_the_person_department(self):
        received = self.answered(self.on_phone(self.chemist, "POST", "/samples/receive", {"code": self.sample.code}))
        again = self.answered(
            self.on_phone(self.second_chemist, "POST", "/samples/receive", {"code": f" {self.sample.code} "})
        )

        handover = self.handover_of(self.department)
        self.assertEqual(handover.received_by_id, self.chemist)
        self.assertTrue(handover.received_at)
        self.assertEqual(received["handover"]["received_by"], self.chemist.name)
        self.assertEqual(again["handover"], received["handover"])
        self.assertFalse(self.handover_of(self.microbiology).received_at)

    def test_a_sample_not_handed_over_to_the_person_department_records_no_receipt_and_says_why(self):
        refused = self.on_phone(self.physicist, "POST", "/samples/receive", {"code": self.sample.code})
        nowhere = self.on_phone(self.receptionist, "POST", "/samples/receive", {"code": self.sample.code})

        self.assertApiRefused(ACTION_REFUSED, refused)
        self.assertIn(self.sample.code, refused.json()["error"]["message"])
        self.assertApiRefused(ACTION_REFUSED, nowhere)
        self.assertFalse(self.sample.handover_ids.filtered("received_at"))
        self.assertApiRefused(INVALID_REQUEST, self.on_phone(self.chemist, "POST", "/samples/receive", {"code": " "}))

    # Claiming testing tasks

    def test_a_tester_claims_the_unassigned_testing_tasks_of_their_department(self):
        sample = self.answered(
            self.on_phone(self.chemist, "POST", f"/samples/{self.sample.id}/claim", {"task_ids": self.lead_task.ids})
        )

        self.assertEqual((self.lead_task.assignee_id, self.lead_task.status), (self.chemist, "assigned"))
        self.assertEqual(sample["tasks"], [])
        self.assertEqual(self.coliforms_task.status, "open")

    def test_a_task_of_another_department_is_refused_and_nothing_is_claimed(self):
        both = (self.lead_task | self.coliforms_task).ids

        refused = self.on_phone(self.chemist, "POST", f"/samples/{self.sample.id}/claim", {"task_ids": both})

        self.assertApiRefused(ACTION_REFUSED, refused)
        self.assertFalse((self.lead_task | self.coliforms_task).assignee_id)

    def test_a_task_someone_else_claimed_first_is_already_claimed(self):
        path = f"/samples/{self.sample.id}/claim"
        self.answered(self.on_phone(self.second_chemist, "POST", path, {"task_ids": self.lead_task.ids}))

        self.assertApiRefused(
            ALREADY_CLAIMED, self.on_phone(self.chemist, "POST", path, {"task_ids": self.lead_task.ids})
        )
        self.assertEqual(self.lead_task.assignee_id, self.second_chemist)
