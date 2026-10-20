from odoo.exceptions import UserError
from odoo.tests import tagged

from .change_request_case import ChangeRequestCase
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_RESULT


@tagged("post_install", "-at_install")
class TestChangeRequestResult(ChangeRequestCase):
    def test_an_approved_change_request_creates_a_new_version_linked_to_the_old_one(self):
        result = self.complete(value_decimals=4)
        request = self.raise_on(result)
        self.limit.max_value = 0.02

        self.sign(request)

        version = self.env[MODEL_TEST_RESULT].browse(request.new_document_id)
        self.assertEqual(request.status, "applied")
        self.assertEqual((version.version, version.replaces_id, version.status), (2, result, "none"))
        self.assertTrue(version.is_reported)
        # The new version keeps the measurement, its decimals and the limit copied with the old one.
        self.assertEqual((version.value, version.value_decimals), (0.008, 4))
        self.assertEqual((version.limit_max, version.unit_id), (0.01, result.unit_id))
        self.assertTrue(result.is_replaced)
        self.assertEqual(self.as_person(result, self.tester).status, "approved")
        self.assertEqual(self.test.status, "testing")
        self.assertEqual(self.test._testing_task().note, request.requested_change)
        message = self.messages(request)
        self.assertEqual(message.subtype_id, self.env.ref("sol_laboratory.event_change_request_approved"))
        self.assertEqual(message.notification_ids.res_partner_id, self.tester.user_id.partner_id)

    def test_the_new_version_is_signed_again_and_reported_in_place_of_the_old_one(self):
        result = self.complete()
        request = self.raise_on(result)
        self.sign(request)
        version = self.env[MODEL_TEST_RESULT].browse(request.new_document_id)

        self.as_person(version, self.tester).value = 0.006
        self.send(version)
        self.approve(version)

        self.assertEqual((version.status, self.test.status, self.request.status), ("approved", "approved", "completed"))
        self.assertEqual(self.report().result_ids, version)

    def test_a_rejected_correction_of_a_reported_result_takes_another_change_request(self):
        result = self.complete()
        self.sign(self.report())
        request = self.raise_on(result)
        self.sign(request)
        version = self.env[MODEL_TEST_RESULT].browse(request.new_document_id)
        self.send(version)
        self.as_person(version, self.head).action_reject("The worksheet still shows a dilution of 5.")
        with self.assertRaises(UserError):
            self.enter(value=0.006)

        again = self.raise_on(version, reason="The digest was diluted 4 times.")
        self.sign(again)

        self.assertEqual(self.env[MODEL_TEST_RESULT].browse(again.new_document_id).version, 3)

    def test_a_rejected_change_request_leaves_the_result_untouched_and_records_the_reason(self):
        result = self.complete()
        request = self.raise_on(result)

        self.as_person(request, self.lab_head).action_reject("The worksheet confirms a dilution of 5.")

        self.assertEqual(request.status, "rejected")
        self.assertEqual(request.rejection_reason, "The worksheet confirms a dilution of 5.")
        self.assertEqual((result.status, result.is_replaced, self.test.status), ("approved", False, "approved"))
        self.assertFalse(self.env[MODEL_TEST_RESULT].search_count([("replaces_id", "=", result.id)]))
        message = self.messages(request)
        self.assertEqual(message.subtype_id, self.env.ref("sol_laboratory.event_change_request_rejected"))
        self.assertIn("The worksheet confirms a dilution of 5.", message.body)
        with self.assertRaises(UserError):
            self.as_person(request, self.lab_head).action_withdraw()

    def test_no_screen_or_api_changes_a_signed_result(self):
        result = self.complete()
        with self.assertRaises(UserError):
            self.as_person(result, self.tester).value = 0.006

        self.sign(self.raise_on(result))

        with self.assertRaises(UserError):
            self.as_person(result, self.tester).value = 0.006
        self.assertEqual(result.value, 0.008)
