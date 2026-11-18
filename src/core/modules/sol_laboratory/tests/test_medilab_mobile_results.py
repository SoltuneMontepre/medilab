from odoo.tests import tagged

from .laboratory_files_case import PASSWORD
from .mobile_phones import PhoneCalls
from .test_result_sanity_check import SanityCheckCase
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    IDEMPOTENCY_CONFLICT,
    INVALID_REQUEST,
    NOT_FOUND,
    PERMISSION_DENIED,
)
from odoo.addons.sol_laboratory.constants.medilab_mobile import ACTION_REFUSED, RESULT_WARNING
from odoo.addons.sol_laboratory.constants.models import MODEL_SIGNATURE, MODEL_TEST_RESULT

NO_ACTIONS = {"edit": False, "sign": False, "reject": False}
CONFIRMED = {"confirmed": True}


@tagged("post_install", "-at_install")
class TestMedilabMobileResults(SanityCheckCase, PhoneCalls):
    """Testing at the bench on Medilab Mobile: the tester enters the lead result of the received sample and sends it,
    and their head of department approves or rejects it on the phone."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for person in (cls.tester, cls.other_tester, cls.head):
            person.user_id.password = PASSWORD

    def enter_on_phone(self, person, body=None, key=None):
        headers = {"Idempotency-Key": key} if key else None
        return self.on_phone(
            person,
            "POST",
            f"/sample-tests/{self.test.id}/results",
            body or {"value": 0.008, "conclusion": "pass"},
            headers=headers,
        )

    def signed_on_phone(self, person, result_id, body=CONFIRMED):
        return self.on_phone(person, "POST", f"/results/{result_id}/sign", body)

    # The sample test

    def test_the_tester_reads_the_test_with_its_unit_decimals_and_regulation(self):
        test = self.answered(self.on_phone(self.tester, "GET", f"/sample-tests/{self.test.id}"))

        self.assertEqual(test["code"], self.sample.code)
        self.assertEqual(test["parameter"], self.parameter.display_name)
        self.assertEqual(test["way"], self.pair.display_name)
        self.assertEqual((test["unit"], test["decimals"]), ("mg/g", 3))
        self.assertEqual(test["regulation"], self.sample.regulation_id.display_name)
        self.assertTrue(test["comparison_requested"])
        self.assertTrue(test["can_enter_result"])
        self.assertIsNone(test["result"])

    def test_a_test_the_person_may_not_read_is_not_found(self):
        self.tester.permission_ids = False

        self.assertApiRefused(NOT_FOUND, self.on_phone(self.tester, "GET", f"/sample-tests/{self.test.id}"))

    # Entering and changing the result

    def test_the_tester_enters_a_result_once_per_idempotency_key(self):
        first = self.answered(self.enter_on_phone(self.tester, key="result-1"))
        again = self.answered(self.enter_on_phone(self.tester, key="result-1"))

        self.assertEqual(again["id"], first["id"])
        result = self.env[MODEL_TEST_RESULT].browse(first["id"])
        self.assertEqual((result.entered_by_id, result.value, result.conclusion), (self.tester.user_id, 0.008, "pass"))
        self.assertEqual(result.created_by_device_id.platform, "android")
        self.assertEqual((first["unit"], first["value_display"], first["limit"]), ("mg/g", "0.008 mg/g", "≤ 0.01 mg/g"))
        self.assertEqual(first["actions"], {"edit": True, "sign": True, "reject": False})
        self.assertApiRefused(
            IDEMPOTENCY_CONFLICT, self.enter_on_phone(self.tester, {"value": 0.009, "conclusion": "pass"}, "result-1")
        )
        test = self.answered(self.on_phone(self.tester, "GET", f"/sample-tests/{self.test.id}"))
        self.assertEqual(test["result"]["id"], first["id"])
        self.assertFalse(test["can_enter_result"])

    def test_a_text_result_is_entered_and_a_draft_is_changed(self):
        result = self.answered(self.enter_on_phone(self.tester, {"value_text": "Not detected", "conclusion": "pass"}))
        self.assertEqual((result["value"], result["value_text"]), (None, "Not detected"))

        changed = self.answered(
            self.on_phone(
                self.tester, "PATCH", f"/results/{result['id']}", {"value_text": None, "value": 0.0042, "decimals": 4}
            )
        )

        self.assertEqual(
            (changed["value"], changed["value_text"], changed["value_display"]), (0.0042, "", "0.0042 mg/g")
        )

    def test_a_result_without_a_value_or_with_an_unknown_field_is_invalid(self):
        self.assertApiRefused(INVALID_REQUEST, self.enter_on_phone(self.tester, {"conclusion": "pass"}))
        self.assertApiRefused(INVALID_REQUEST, self.enter_on_phone(self.tester, {"value": 1, "machine_id": 1}))

    def test_a_person_without_the_permission_to_enter_results_is_refused(self):
        self.tester.permission_ids = self.permissions("sample_test.read.all")

        self.assertApiRefused(PERMISSION_DENIED, self.enter_on_phone(self.tester))

    def test_a_refusal_of_the_result_answers_action_refused_with_its_message(self):
        response = self.enter_on_phone(self.tester, {"value": 0.008, "conclusion": "maybe"})
        self.assertApiRefused(INVALID_REQUEST, response)
        self.sample.regulation_id = False
        self.test.invalidate_recordset()

        refused = self.enter_on_phone(self.tester, {"value": 0.008, "conclusion": "pass"})

        self.assertApiRefused(ACTION_REFUSED, refused)
        self.assertIn("conclusion", refused.json()["error"]["message"])

    # Sending

    def test_sending_needs_the_confirmation_step(self):
        result = self.answered(self.enter_on_phone(self.tester))

        self.assertApiRefused(INVALID_REQUEST, self.signed_on_phone(self.tester, result["id"], {}))
        self.assertApiRefused(INVALID_REQUEST, self.signed_on_phone(self.tester, result["id"], {"confirmed": False}))

    def test_a_result_with_warnings_is_sent_only_once_they_are_acknowledged(self):
        result = self.answered(self.enter_on_phone(self.tester, {"value": 0.0095, "conclusion": "pass"}))
        self.assertTrue(result["warnings"])

        refused = self.signed_on_phone(self.tester, result["id"])
        self.assertApiRefused(RESULT_WARNING, refused)
        self.assertIn("regulation limit", refused.json()["error"]["message"])
        sent = self.answered(
            self.signed_on_phone(self.tester, result["id"], {"confirmed": True, "warnings_acknowledged": True})
        )

        self.assertEqual(sent["status"], "requested")
        self.assertTrue(sent["warned"])
        self.assertEqual(sent["warnings"], result["warnings"])

    def test_a_result_sent_on_the_phone_waits_for_the_head_with_the_testers_signature(self):
        result = self.answered(self.enter_on_phone(self.tester))

        sent = self.answered(self.signed_on_phone(self.tester, result["id"]))

        self.assertEqual(sent["status"], "requested")
        self.assertEqual(sent["actions"], NO_ACTIONS)
        signatures = self.env[MODEL_SIGNATURE].search(
            [("document_model", "=", MODEL_TEST_RESULT), ("document_id", "=", result["id"])]
        )
        self.assertEqual(signatures.signer_id, self.tester)
        self.assertEqual(self.task.status, "done")
        waiting = self.answered(self.on_phone(self.head, "GET", "/results?awaiting=me"))
        self.assertEqual([row["id"] for row in waiting["results"]], [result["id"]])
        self.assertIsNone(waiting["next_after"])
        self.assertEqual(self.answered(self.on_phone(self.tester, "GET", "/results?awaiting=me"))["results"], [])
        head_view = self.answered(self.on_phone(self.head, "GET", f"/results/{result['id']}"))
        self.assertEqual(head_view["actions"], {"edit": False, "sign": True, "reject": True})

    # Approving and rejecting

    def test_the_head_approves_and_the_result_becomes_read_only(self):
        result = self.answered(self.enter_on_phone(self.tester))
        self.answered(self.signed_on_phone(self.tester, result["id"]))

        approved = self.answered(self.signed_on_phone(self.head, result["id"]))

        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["actions"], NO_ACTIONS)
        self.assertEqual(self.test.status, "approved")
        changed = self.on_phone(self.tester, "PATCH", f"/results/{result['id']}", {"value": 0.007})
        self.assertApiRefused(ACTION_REFUSED, changed)

    def test_rejecting_without_a_reason_is_refused(self):
        result = self.answered(self.enter_on_phone(self.tester))
        self.answered(self.signed_on_phone(self.tester, result["id"]))

        for reason in ("", "   "):
            with self.subTest(reason=reason):
                path = f"/results/{result['id']}/reject"
                self.assertApiRefused(ACTION_REFUSED, self.on_phone(self.head, "POST", path, {"reason": reason}))
        rejected = self.answered(
            self.on_phone(self.head, "POST", f"/results/{result['id']}/reject", {"reason": "Recalibrate the AAS."})
        )

        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(rejected["rejection_reason"], "Recalibrate the AAS.")
        self.assertEqual(self.test.status, "testing")

    def test_a_tester_cannot_approve_or_reject(self):
        result = self.answered(self.enter_on_phone(self.tester))
        self.answered(self.signed_on_phone(self.tester, result["id"]))

        self.assertApiRefused(ACTION_REFUSED, self.signed_on_phone(self.other_tester, result["id"]))
        path = f"/results/{result['id']}/reject"
        self.assertApiRefused(ACTION_REFUSED, self.on_phone(self.other_tester, "POST", path, {"reason": "Too high."}))

    def test_only_a_person_who_signs_after_the_tester_is_offered_the_results_to_sign(self):
        def can_sign(person):
            return self.answered(self.on_phone(person, "GET", "/me"))["can"]["sign_results"]

        self.assertTrue(can_sign(self.head))
        self.assertFalse(can_sign(self.tester))

    def test_a_head_approves_their_own_result_on_the_phone(self):
        self.take_task(self.head)
        result = self.answered(self.enter_on_phone(self.head))

        sent = self.answered(self.signed_on_phone(self.head, result["id"]))
        self.assertEqual(sent["actions"]["sign"], True)
        approved = self.answered(self.signed_on_phone(self.head, result["id"]))

        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["entered_by"], self.head.user_id.name)

    def test_a_result_the_person_may_not_read_is_not_found(self):
        result = self.answered(self.enter_on_phone(self.tester))
        self.other_tester.permission_ids = self.permissions("sample_test.read.all")

        self.assertApiRefused(NOT_FOUND, self.on_phone(self.other_tester, "GET", f"/results/{result['id']}"))
