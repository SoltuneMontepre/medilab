from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from .result_case import RESULT_PERMISSIONS, ResultCase
from odoo.addons.sol_laboratory.constants.models import MODEL_APPROVAL_LEVEL, MODEL_ROLE, MODEL_SIGNATURE
from odoo.addons.sol_laboratory.services.record_id import persisted_id


@tagged("post_install", "-at_install")
class TestSigningLevels(ResultCase):
    """The head holds only the head's role here, and a second head of the department approves what the first cannot."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.chain = cls.signing_chain()
        cls.tester_level, cls.head_level = cls.chain.level_ids.sorted("sequence")
        cls.head.role_ids = cls.head_level.role_id
        cls.other_head = cls.create_person(
            "Vo Thi Mai", cls.department, "mai.vo", permissions=RESULT_PERMISSIONS, roles=cls.head_level.role_id
        )

    def rows(self, result):
        return self.env[MODEL_SIGNATURE].search(
            [("document_model", "=", result._name), ("document_id", "=", result.id)], order="id"
        )

    def test_a_head_signs_the_tester_level_in_their_own_name_and_then_no_other_level(self):
        result = self.enter()

        self.send(result, self.head)

        row = self.rows(result)
        self.assertEqual(
            (row.signer_id, row.level_id, row.signer_role), (self.head, self.tester_level, self.head_level.role_id.name)
        )
        self.assertFalse(self.as_person(result, self.head).approval_can_sign)
        with self.assertRaises(UserError):
            self.approve(result)
        self.as_person(result, self.other_head).action_sign()
        self.assertEqual(result.status, "approved")

    def test_a_head_rejects_at_the_tester_level_in_their_own_name_when_it_can_reject(self):
        self.tester_level.can_reject = True
        result = self.enter()

        self.as_person(result, self.head).action_reject("The blank read above the limit of quantification.")

        row = self.rows(result)
        self.assertEqual((row.signer_id, row.level_id, row.decision), (self.head, self.tester_level, "rejected"))

    def test_a_tester_cannot_sign_the_level_of_the_head(self):
        result = self.enter()
        self.send(result)

        self.assertFalse(self.as_person(result, self.other_tester).approval_can_sign)
        with self.assertRaises(UserError):
            self.as_person(result, self.other_tester).action_sign()

    def test_a_head_without_the_tester_role_sends_then_approves_a_result_they_entered(self):
        result = self.enter(person=self.head)

        self.send(result, self.head)
        self.approve(result)

        self.assertEqual(result.status, "approved")
        self.assertEqual(
            [(row.signer_id, row.level_id) for row in self.rows(result)],
            [(self.head, self.tester_level), (self.head, self.head_level)],
        )

    def test_a_level_added_during_signing_applies_only_to_results_whose_signing_starts_later(self):
        other_test = self.add_test()
        started = self.enter()
        self.send(started)
        lab_head_role = self.env[MODEL_ROLE].create({"code": "qa_lab_head", "name": "Lab head"})
        self.env[MODEL_APPROVAL_LEVEL].create(
            {"chain_id": self.chain.id, "sequence": 30, "name": "Lab head", "role_id": lab_head_role.id}
        )
        later = self.enter(test=other_test)
        self.send(later)

        self.approve(started)
        self.approve(later)

        self.assertEqual(started.status, "approved")
        self.assertEqual(later.status, "requested")

    def test_changing_a_level_during_signing_keeps_its_old_role_for_started_results(self):
        other_test = self.add_test()
        started = self.enter()
        self.send(started)
        old_role = self.head_level.role_id
        new_role = self.env[MODEL_ROLE].create({"code": "qa_new_head", "name": "New head"})

        self.head_level.role_id = new_role

        self.assertFalse(self.head_level.active)
        self.assertEqual(self.head_level.role_id, old_role)
        replacement = self.chain.level_ids.sorted("sequence")[-1]
        self.assertEqual((replacement.sequence, replacement.role_id), (self.head_level.sequence, new_role))
        self.approve(started)
        self.assertEqual(started.status, "approved")
        later = self.enter(test=other_test)
        self.send(later)
        self.assertFalse(self.as_person(later, self.head).approval_can_sign)

    def test_removing_a_level_during_signing_archives_it_for_started_results(self):
        started = self.enter()
        self.send(started)

        self.chain.level_ids = [Command.delete(persisted_id(self.head_level))]

        self.assertTrue(self.head_level.exists())
        self.assertFalse(self.head_level.active)
        self.assertEqual(self.chain.level_ids, self.tester_level)
        self.approve(started)
        self.assertEqual(started.status, "approved")

    def test_a_level_no_result_signed_at_is_changed_and_deleted_in_place(self):
        level = self.env[MODEL_APPROVAL_LEVEL].create(
            {"chain_id": self.chain.id, "sequence": 30, "name": "Check", "role_id": self.head_level.role_id.id}
        )

        level.can_reject = False
        self.assertTrue(level.active)
        level.unlink()

        self.assertFalse(level.exists())
