from odoo.tests import tagged

from .change_request_case import ChangeRequestCase
from odoo.addons.sol_laboratory.constants.approvals import PURPOSE_CHANGE_REQUEST
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_APPROVAL_LEVEL,
    MODEL_ROLE,
    MODEL_TEST_RESULT,
)

WAITING_EVENT = "sol_laboratory.event_change_request_waiting"


@tagged("post_install", "-at_install")
class TestChangeRequestWaiting(ChangeRequestCase):
    """The people who sign the level a change request waits for are told when it reaches that level."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lab_head.user_id.notification_type = "inbox"

    def waiting(self, request):
        return self.messages(request, WAITING_EVENT).sorted("id")

    def add_quality_manager_level(self):
        """A second level of the result change-request chain, which a quality manager signs."""
        chain = self.approval_chain(MODEL_TEST_RESULT, (), PURPOSE_CHANGE_REQUEST)
        role = self.env[MODEL_ROLE].create({"code": "qa_quality_manager", "name": "Quality manager"})
        self.env[MODEL_APPROVAL_LEVEL].create(
            {"chain_id": chain.id, "sequence": 99, "name": "Quality manager", "role_id": role.id, "can_reject": True}
        )
        manager = self.create_person(
            "Phan Thi Thu",
            login="thu.phan",
            permissions=("change_request.read.all", "change_request.sign.all", "test_result.read.all"),
            roles=role,
        )
        manager.user_id.notification_type = "inbox"
        return manager

    def test_raising_a_change_request_tells_the_people_who_sign_its_first_level(self):
        request = self.raise_on(self.complete())

        message = self.waiting(request)
        self.assertEqual(len(message), 1)
        level = request._approval_levels()[:1]
        self.assertEqual(message.notification_key, f"change_request:{request.id}:1:{level.id}:waiting")
        self.assertIn(self.lab_head.user_id.partner_id, message.notification_ids.res_partner_id)
        self.assertNotIn(self.tester.user_id.partner_id, message.notification_ids.res_partner_id)
        self.assertIn(request.code, message.body or "")

    def test_the_next_level_is_told_once_the_level_before_it_signs(self):
        manager = self.add_quality_manager_level()
        request = self.raise_on(self.complete())
        self.assertNotIn(manager.user_id.partner_id, self.waiting(request).notification_ids.res_partner_id)

        self.sign(request)

        self.assertEqual(request.status, "requested")
        messages = self.waiting(request)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[-1].notification_ids.res_partner_id, manager.user_id.partner_id)

        self.as_person(request, manager).action_sign()

        self.assertEqual(request.status, "applied")
        self.assertEqual(len(self.waiting(request)), 2)

    def test_signing_the_last_level_tells_no_signer(self):
        request = self.raise_on(self.complete())

        self.sign(request)

        self.assertEqual(request.status, "applied")
        self.assertEqual(len(self.waiting(request)), 1)

    def test_correcting_a_reported_result_tells_the_signers_of_the_report_change_request(self):
        result = self.complete()
        self.sign(self.report())

        request = self.raise_on(result)

        report_request = request.report_change_request_id
        self.assertTrue(report_request)
        self.assertIn(self.lab_head.user_id.partner_id, self.waiting(report_request).notification_ids.res_partner_id)
