import re

from odoo.tests import tagged

from .laboratory_file_locks_case import LaboratoryFileLocksCase
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    EDITED_ONLINE,
    FILE_READ,
    FILE_WRITE,
    LOCKED,
    RESTORED,
)
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError


@tagged("post_install", "-at_install")
class TestLaboratoryFileLockSaves(LaboratoryFileLocksCase):
    def restore(self, file, user):
        return file._add_version(
            sha256=self.first.sha256,
            size=self.first.size,
            storage_key=self.first.storage_key,
            source=RESTORED,
            user=user,
            restored_from=self.first,
        )

    def test_nobody_else_saves_a_locked_file_whoever_stores_it_and_with_whatever_rights(self):
        self.save(self.file, "calibration 2")
        self.lock_as(self.tester)
        saves = {
            "upload": lambda file: self.save(
                file, "member's copy", user=self.member, base_version=file.current_version_id
            ),
            "online save": lambda file: self.save(file, "edited online", user=self.member, source=EDITED_ONLINE),
            "restore": lambda file: self.restore(file, self.member),
        }
        for name, save in saves.items():
            for file in (self.file.with_user(self.member), self.file.sudo()):
                with self.subTest(save=name, superuser=file.env.su):
                    self.assertRefused(LOCKED, save, file)
        self.assertEqual(self.file.version_ids.sorted("number").mapped("number"), [1, 2])

    def test_the_holder_saves_the_locked_file_and_keeps_the_lock(self):
        lock = self.lock_as(self.tester)
        expires_at = lock.expires_at

        version = self.save(self.file, "calibration 2")

        self.assertEqual(self.file.current_version_id, version)
        self.assertRecordValues(lock, [{"status": "active", "expires_at": expires_at}])

    def test_releasing_or_expiring_a_lock_lets_others_save_again(self):
        self.lock_as(self.tester)
        self.file.with_user(self.tester)._unlock()
        self.save(self.file, "member's copy", user=self.member)

        lock = self.lock_as(self.tester)
        self.pass_expiry(lock)
        version = self.save(self.file, "member's second copy", user=self.member)

        self.assertEqual(self.file.current_version_id, version)

    def test_others_are_refused_writing_a_locked_file_early_and_still_read_it(self):
        self.lock_as(self.tester)
        member_file = self.file.with_user(self.member)

        with self.assertRaisesRegex(LaboratoryFileError, re.escape(self.tester.name)):
            member_file._check_file_access(FILE_WRITE)
        self.assertRefused(LOCKED, member_file._check_file_access, FILE_WRITE)
        member_file._check_file_access(FILE_READ)
        self.file.with_user(self.tester)._check_file_access(FILE_WRITE)

    def test_locking_leaves_when_the_file_was_last_saved(self):
        self.env.flush_all()
        last_saved = (self.file.write_date, self.file.write_uid)

        self.lock_as(self.member)
        self.file.invalidate_recordset()

        self.assertEqual((self.file.write_date, self.file.write_uid), last_saved)
