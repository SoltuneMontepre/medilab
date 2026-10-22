from odoo.exceptions import UserError
from odoo.tests import tagged

from .laboratory_signing_case import LaboratorySigningCase
from odoo.addons.sol_laboratory.constants.approvals import STATE_NONE, STATE_REJECTED
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FILE_VERSION_REJECT, MODEL_MAIL_MESSAGE


@tagged("post_install", "-at_install")
class TestLaboratoryFileVersionRejection(LaboratorySigningCase):
    def reject(self, version, reason):
        wizard = self.env[MODEL_LABORATORY_FILE_VERSION_REJECT].with_user(self.head.user_id)
        return wizard.create({"version_id": version.id, "reason": reason}).action_reject()

    def notices(self, version):
        return self.env[MODEL_MAIL_MESSAGE].search([("model", "=", version._name), ("res_id", "=", version.id)])

    def test_rejecting_tells_the_person_who_saved_the_version_why(self):
        self.saver.user_id.notification_type = "inbox"
        version = self.result_version()

        self.reject(version, "The calibration curve is missing.")

        self.assertEqual(version.approval_state, STATE_REJECTED)
        notice = self.notices(version)
        self.assertEqual(notice.subtype_id, self.env.ref("sol_laboratory.event_laboratory_file_version_rejected"))
        self.assertIn("The calibration curve is missing.", notice.body)
        self.assertEqual(notice.notification_ids.res_partner_id, self.saver.user_id.partner_id)

    def test_rejecting_without_a_reason_is_refused(self):
        version = self.result_version()

        for reason in ("", "  "):
            with self.subTest(reason=reason), self.assertRaises(UserError):
                self.reject(version, reason)
        self.assertEqual(version.approval_state, STATE_NONE)
        self.assertFalse(self.notices(version))

    def test_a_version_rejected_again_after_a_withdrawal_tells_again(self):
        version = self.result_version()
        self.reject(version, "The calibration curve is missing.")
        self.as_person(version, self.head).action_withdraw()

        self.reject(version, "The blank is above the limit of detection.")

        self.assertEqual(len(self.notices(version)), 2)
