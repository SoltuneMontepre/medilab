from odoo.exceptions import AccessError
from odoo.tests import tagged

from .laboratory_files_case import LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.laboratory_files import DEVICE_KEY_SCOPE, DEVICE_REVOKED, INVALID_KEY
from odoo.addons.sol_laboratory.constants.models import MODEL_RES_USERS_APIKEYS


@tagged("post_install", "-at_install")
class TestLaboratoryDeviceRevocation(LaboratoryFilesCase):
    def setUp(self):
        super().setUp()
        self.lost, self.lost_key = self.sign_in(self.tester, "lost-laptop")
        self.kept, self.kept_key = self.sign_in(self.tester, "laboratory-pc")

    def test_a_revoked_computer_is_refused_at_once_and_the_others_keep_working(self):
        self.lost.with_user(self.administrator).action_revoke()

        self.assertEqual(self.lost.status, "revoked")
        self.assertIsNone(
            self.env[MODEL_RES_USERS_APIKEYS]._check_credentials(scope=DEVICE_KEY_SCOPE, key=self.lost_key)
        )
        self.assertRefused(INVALID_KEY, self.lost.with_user(self.tester)._from_key, self.lost_key)
        self.assertEqual(self.device_of(self.kept_key), self.kept)
        self.assertIn(self.tester, self.folder.member_ids.user_id)

    def test_a_revoked_computer_cannot_sign_in_again(self):
        self.lost.with_user(self.administrator).action_revoke()

        self.assertRefused(DEVICE_REVOKED, self.sign_in, self.tester, "lost-laptop")
        device, key = self.sign_in(self.tester, "new-installation")
        self.assertEqual(self.device_of(key), device)

    def test_a_person_revoking_their_own_computer_revokes_it_for_good(self):
        self.lost.with_user(self.tester).action_revoke()

        self.assertEqual(self.lost.status, "revoked")
        self.assertRefused(DEVICE_REVOKED, self.sign_in, self.tester, "lost-laptop")
        self.assertEqual(self.device_of(self.kept_key), self.kept)

    def test_a_person_cannot_revoke_someone_elses_computer(self):
        with self.assertRaises(AccessError):
            self.lost.with_user(self.member).action_revoke()

        self.assertEqual(self.lost.status, "signed_in")

    def test_a_key_removed_from_the_preferences_signs_the_computer_out(self):
        self.lost.api_key_id._remove()

        self.assertEqual(self.lost.status, "signed_out")
        self.assertRefused(INVALID_KEY, self.lost.with_user(self.tester)._from_key, self.lost_key)
        device, key = self.sign_in(self.tester, "lost-laptop")
        self.assertEqual(self.device_of(key), device)

    def test_a_computer_whose_key_was_removed_elsewhere_is_still_revoked(self):
        self.lost.api_key_id._remove()

        self.lost.with_user(self.administrator).action_revoke()

        self.assertEqual(self.lost.status, "revoked")
        self.assertRefused(DEVICE_REVOKED, self.sign_in, self.tester, "lost-laptop")
