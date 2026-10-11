from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REQUEST_READER_GROUP


@tagged("post_install", "-at_install")
class TestTestRequestLifecycle(RequestCase):
    def test_request_starts_as_draft_with_expected_samples_and_waiting_tests(self):
        self.assertEqual(self.request.status, "draft")
        self.assertEqual(self.sample.status, "expected")
        self.assertEqual(self.sample.test_ids.status, "waiting")

    def test_request_without_order_skips_the_paid_step(self):
        self.request.action_confirm()

        self.assertEqual(self.request.status, "confirmed")
        with self.assertRaises(UserError):
            self.request._set_status("paid")
        self.request._set_status("sample_received")
        self.assertEqual(self.request.status, "sample_received")

    def test_request_cannot_skip_a_step(self):
        with self.assertRaises(UserError):
            self.request._set_status("testing")

    def test_cancelling_cancels_its_samples_and_their_tests(self):
        editor = new_test_user(
            self.env,
            login="request.editor",
            groups=f"base.group_user,{TEST_REQUEST_READER_GROUP},sol_laboratory.group_permission_test_request_edit_all",
        )
        self.request.action_confirm()
        self.request.with_user(editor).action_cancel()

        self.assertEqual(self.request.status, "cancelled")
        self.assertEqual(self.sample.status, "cancelled")
        self.assertEqual(self.sample.test_ids.status, "cancelled")
        with self.assertRaises(UserError):
            self.request.action_confirm()
