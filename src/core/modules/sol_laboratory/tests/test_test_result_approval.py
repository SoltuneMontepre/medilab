from odoo.exceptions import UserError
from odoo.tests import tagged

from .result_case import RESULT_PERMISSIONS, ResultCase
from odoo.addons.sol_laboratory.constants.models import MODEL_APPROVAL_LEVEL, MODEL_DEPARTMENT, MODEL_SIGNATURE


@tagged("post_install", "-at_install")
class TestTestResultApproval(ResultCase):
    def test_approving_the_reported_result_closes_the_testing_task(self):
        result = self.enter()
        self.send(result)

        self.approve(result)

        self.assertEqual(result.status, "approved")
        self.assertEqual(self.test.status, "approved")
        self.assertEqual(self.task.status, "done")

    def test_a_sample_is_completed_once_every_result_is_approved(self):
        arsenic = self.add_test()
        lead = self.enter()
        self.send(lead)
        self.approve(lead)
        self.assertEqual(self.sample.status, "testing")

        other = self.enter(test=arsenic)
        self.send(other)
        self.assertEqual(self.sample.status, "awaiting_approval")
        self.assertEqual(self.request.status, "awaiting_approval")
        self.approve(other)

        self.assertEqual(self.sample.status, "completed")
        self.assertEqual(self.request.status, "completed")

    def test_the_signatures_of_a_result_record_no_document_hash(self):
        result = self.enter()
        self.send(result)

        signatures = self.env[MODEL_SIGNATURE].search(
            [("document_model", "=", result._name), ("document_id", "=", result.id)]
        )
        self.assertTrue(signatures)
        self.assertFalse(any(signatures.mapped("document_hash")))

    def signers(self, result):
        rows = self.env[MODEL_SIGNATURE].search(
            [("document_model", "=", result._name), ("document_id", "=", result.id)], order="id"
        )
        return [(row.signer_id, row.level_id) for row in rows]

    def test_a_head_approves_a_result_they_entered_that_another_person_sent(self):
        tester_level, head_level = self.signing_chain().level_ids.sorted("sequence")
        result = self.enter(person=self.head)
        self.send(result, self.other_tester)

        self.assertTrue(self.as_person(result, self.head).approval_can_sign)
        self.approve(result)

        self.assertEqual(result.status, "approved")
        self.assertEqual(self.signers(result), [(self.other_tester, tester_level), (self.head, head_level)])

    def test_a_head_who_is_the_only_signer_sends_then_approves_their_own_result(self):
        tester_level, head_level = self.signing_chain().level_ids.sorted("sequence")
        result = self.enter(person=self.head)
        self.assertEqual(result.status, "none")

        self.send(result, self.head)
        self.assertEqual(result.status, "requested")
        self.approve(result)

        self.assertEqual(result.status, "approved")
        self.assertEqual(self.signers(result), [(self.head, tester_level), (self.head, head_level)])

    def test_a_tester_cannot_approve_a_result_they_entered(self):
        result = self.enter()
        self.send(result)

        self.assertFalse(self.as_person(result, self.tester).approval_can_sign)
        with self.assertRaises(UserError):
            self.as_person(result, self.tester).action_sign()

    def test_a_head_of_another_department_cannot_approve(self):
        department = self.env[MODEL_DEPARTMENT].create({"name": "Microbiology"})
        head_level = self.signing_chain().level_ids.sorted("sequence")[-1]
        other_head = self.create_person("Pham Van Long", department, login="long.pham", roles=head_level.role_id)
        self.grant(other_head, *RESULT_PERMISSIONS)
        result = self.enter()
        self.send(result)

        with self.assertRaises(UserError):
            self.as_person(result, other_head).action_sign()
        self.assertEqual(result.status, "requested")

    def test_an_entrant_cannot_sign_a_middle_approval_level(self):
        tester_level = self.signing_chain().level_ids.sorted("sequence")[0]
        self.env[MODEL_APPROVAL_LEVEL].create(
            {
                "chain_id": tester_level.chain_id.id,
                "sequence": 15,
                "name": "Checker",
                "role_id": tester_level.role_id.id,
            }
        )
        result = self.enter()
        self.send(result, self.other_tester)

        self.assertTrue(self.as_person(result, self.head).approval_can_sign)
        with self.assertRaises(UserError):
            self.as_person(result, self.tester).action_sign()

    def test_rejecting_keeps_the_result_sends_the_test_back_and_tells_the_tester(self):
        self.tester.user_id.notification_type = "inbox"
        result = self.enter()
        self.send(result)

        self.as_person(result, self.head).action_reject("The blank read above the limit of detection.")

        self.assertEqual(result.status, "rejected")
        self.assertEqual(self.test.status, "testing")
        self.assertEqual(self.task.status, "assigned")
        message = self.env["mail.message"].search([("model", "=", result._name), ("res_id", "=", result.id)])
        self.assertEqual(message.subtype_id, self.env.ref("sol_laboratory.event_test_result_rejected"))
        self.assertIn("The blank read above the limit of detection.", (message.body or ""))
        self.assertEqual(message.notification_ids.res_partner_id, self.tester.user_id.partner_id)
        retest = self.enter(value=0.009)
        self.assertTrue(retest.is_reported)
        self.assertEqual(result.status, "rejected")

    def test_the_tester_withdraws_a_sent_result_until_the_head_acts(self):
        result = self.enter()
        self.send(result)

        self.as_person(result, self.tester).action_withdraw()

        self.assertEqual(result.status, "none")
        self.assertEqual(self.test.status, "testing")

    def test_an_approved_or_rejected_result_cannot_be_withdrawn(self):
        arsenic = self.add_test()
        approved = self.enter()
        self.send(approved)
        self.approve(approved)
        rejected = self.enter(test=arsenic)
        self.send(rejected)
        self.as_person(rejected, self.head).action_reject("The duplicate readings differ by 20%.")

        for result in (approved, rejected):
            with self.subTest(status=result.status), self.assertRaises(UserError):
                self.as_person(result, self.head).action_withdraw()
