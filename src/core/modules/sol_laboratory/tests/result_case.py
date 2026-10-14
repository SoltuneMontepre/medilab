from .scheduling_case import SchedulingCase
from odoo.addons.sol_laboratory.constants.approvals import PURPOSE_SIGNING
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_APPROVAL_CHAIN,
    MODEL_APPROVAL_LEVEL,
    MODEL_PARAMETER_METHOD,
    MODEL_REGULATION,
    MODEL_REGULATION_LIMIT,
    MODEL_ROLE,
    MODEL_SAMPLE_TEST,
    MODEL_TEST_RESULT,
)

RESULT_PERMISSIONS = ("test_result.read.all", "test_result.create.all", "test_result.edit.all", "test_result.sign.all")


class ResultCase(SchedulingCase):
    """The received lead sample is compared with a regulation allowing at most 0.01 mg/g. Its results are signed by a
    tester, then approved by the head of the department; the head also holds the tester role."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        tester_level, head_level = cls.signing_chain().level_ids.sorted("sequence")
        for person in (cls.tester, cls.other_tester, cls.head):
            cls.grant(person, *RESULT_PERMISSIONS)
        cls.grant(cls.head, "sample_test.edit.all")
        (cls.tester | cls.other_tester).role_ids = tester_level.role_id
        cls.head.role_ids = tester_level.role_id | head_level.role_id
        regulation = cls.env[MODEL_REGULATION].create({"code": "QCVN 01-1:2018/BYT", "name": "Domestic water"})
        cls.limit = cls.env[MODEL_REGULATION_LIMIT].create(
            {
                "regulation_id": regulation.id,
                "parameter_id": cls.parameter.id,
                "unit_id": cls.unit.id,
                "max_set": True,
                "max_value": 0.01,
            }
        )
        cls.pair.result_decimals = 3
        cls.request.status = "sample_received"
        cls.sample.write({"status": "received", "regulation_id": regulation.id})
        cls.task = cls.testing_task(cls.test, cls.tester)

    @classmethod
    def signing_chain(cls):
        """A tester signs first and cannot reject, then the head of the department; the demo data may have made it."""
        chain = cls.env[MODEL_APPROVAL_CHAIN].search(
            [("document_model", "=", MODEL_TEST_RESULT), ("purpose", "=", PURPOSE_SIGNING)]
        )
        if chain:
            return chain
        chain = cls.env[MODEL_APPROVAL_CHAIN].create(
            {"document_model": MODEL_TEST_RESULT, "purpose": PURPOSE_SIGNING, "name": "Test result signing"}
        )
        for sequence, name, code, can_reject in ((10, "Tester", "qa_tester", False), (20, "Head", "qa_head", True)):
            cls.env[MODEL_APPROVAL_LEVEL].create(
                {
                    "chain_id": chain.id,
                    "sequence": sequence,
                    "name": name,
                    "role_id": cls.env[MODEL_ROLE].create({"code": code, "name": name}).id,
                    "same_department": True,
                    "can_reject": can_reject,
                }
            )
        return chain

    @classmethod
    def add_test(cls):
        """An arsenic test on the same sample, tested by the same department and assigned to the tester."""
        arsenic = cls.create_parameter("Arsenic (As)", cls.group)
        cls.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": arsenic.id,
                "method_id": cls.method.id,
                "unit_id": cls.unit.id,
                "department_id": cls.department.id,
                "is_default": True,
            }
        )
        test = cls.env[MODEL_SAMPLE_TEST].create({"sample_id": cls.sample.id, "parameter_id": arsenic.id})
        cls.testing_task(test, cls.tester)
        return test

    @classmethod
    def enter(cls, person=None, test=None, **values):
        values = {"value": 0.008, "conclusion": "pass", **values}
        return (
            cls.env[MODEL_TEST_RESULT]
            .with_user((person or cls.tester).user_id)
            .create({"sample_test_id": (test or cls.test).id, **values})
        )

    def send(self, result, person=None):
        self.as_person(result, person or self.tester).action_sign()

    def approve(self, result):
        self.as_person(result, self.head).action_sign()
