from odoo.exceptions import UserError
from odoo.tests import tagged

from .laboratory_file_locks_case import LaboratoryFileLocksCase
from odoo.addons.sol_laboratory.constants.laboratory_files import LOCKED, PERMISSION_DENIED


@tagged("post_install", "-at_install")
class TestLaboratoryFileLockRelease(LaboratoryFileLocksCase):
    def test_an_administrator_releases_a_lock_someone_left_and_others_save_again(self):
        lock = self.lock_as(self.tester)
        self.assertRefused(LOCKED, self.save, self.file, "member's copy", self.member)

        lock.with_user(self.administrator).action_release()

        self.assertRecordValues(lock, [{"status": "released", "released_by_id": self.administrator.id}])
        self.assertTrue(lock.released_at)
        version = self.save(self.file, "member's copy", self.member)
        self.assertEqual(self.file.current_version_id, version)

    def test_only_folder_administrators_release_a_lock(self):
        lock = self.lock_as(self.tester)

        for user in (self.member, self.tester):
            with self.subTest(user=user.login):
                self.assertRefused(PERMISSION_DENIED, lock.with_user(user).action_release)
        self.assertEqual(lock.status, "active")

    def test_a_lock_past_its_expiry_is_recorded_as_expired_and_an_ended_one_is_not_released(self):
        lock = self.lock_as(self.tester)
        self.pass_expiry(lock)

        lock.with_user(self.administrator).action_release()

        self.assertRecordValues(lock, [{"status": "expired", "released_by_id": False}])
        with self.assertRaises(UserError):
            lock.with_user(self.administrator).action_release()
