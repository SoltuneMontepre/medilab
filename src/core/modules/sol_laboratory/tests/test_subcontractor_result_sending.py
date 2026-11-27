from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from .dispatch_case import DispatchCase
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.models import MODEL_SIGNATURE

SENT_EVENT = "sol_laboratory.event_test_result_sent"


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestSubcontractorResultSending(DispatchCase):
    """The sample is compared with no regulation, so the subcontractor's result needs no conclusion: entering it on the
    portal sends it to the head of the department, who heads Chemistry."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sample.regulation_id = False
        cls.department.manager_id = cls.head.employee_id
        cls.head.user_id.notification_type = "inbox"

    def signatures(self, result):
        return self.env[MODEL_SIGNATURE].search(
            [("document_model", "=", result._name), ("document_id", "=", result.id)]
        )

    def sent_notices(self, result):
        return self.env["mail.message"].search(
            [
                ("model", "=", result._name),
                ("res_id", "=", result.id),
                ("subtype_id", "=", self.env.ref(SENT_EVENT).id),
            ]
        )

    def test_entering_a_result_on_the_portal_sends_it_to_the_head_signed_by_the_subcontractor_person(self):
        result = self.enter_on_portal(self.receive_dispatch(self.outsource()), "0.008")

        self.assertEqual(result.status, "requested")
        self.assertEqual(self.test.status, "result_entered")
        signature = self.signatures(result)
        self.assertEqual(signature.level_id, result._approval_levels()[:1])
        self.assertEqual(signature.signer_name, "Nguyen Thi Lan")
        self.assertEqual(signature.signer_role, self.northern.name)
        self.assertFalse(signature.signer_id)
        self.assertEqual(self.sent_notices(result).notification_ids.res_partner_id, self.head.user_id.partner_id)
        self.assertTrue(self.as_person(result, self.head).approval_can_sign)

    def test_the_head_approves_the_subcontractor_result_like_any_other(self):
        result = self.enter_on_portal(self.receive_dispatch(self.outsource()), "0.008")

        self.approve(result)

        self.assertEqual(result.status, "approved")
        self.assertEqual(self.test.status, "approved")

    def test_a_rejected_subcontractor_result_sends_the_test_back_for_a_new_result(self):
        dispatch = self.receive_dispatch(self.outsource())
        result = self.enter_on_portal(dispatch, "0.008")

        self.as_person(result, self.head).action_reject("The blank was contaminated.")

        self.assertEqual(result.status, "rejected")
        self.assertEqual(self.test.status, "outsourced")
        retest = self.enter_on_portal(dispatch, "0.006")
        self.assertTrue(retest.is_reported)
        self.assertEqual(retest.status, "requested")

    def test_nobody_withdraws_the_signature_of_the_subcontractor_person(self):
        result = self.enter_on_portal(self.receive_dispatch(self.outsource()), "0.008")

        with self.assertRaises(UserError):
            result.with_user(self.northern_user).sudo().action_withdraw()
        with self.assertRaises(UserError):
            result.sudo().action_withdraw()
        self.assertEqual(result.status, "requested")
