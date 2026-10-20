from datetime import datetime, timedelta

from freezegun import freeze_time
from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .laboratory_file_locks_case import LaboratoryFileLocksCase
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    FOLDER_DISABLED,
    LOCKED,
    NOT_FOUND,
    NOT_LOCKABLE,
    NOT_LOCKED,
    PERMISSION_DENIED,
    RAW_DATA,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FILE_LOCK, MODEL_RES_CONFIG_SETTINGS
from odoo.addons.sol_laboratory.constants.settings import LABORATORY_FILE_LOCK_PARAMETER

LOCKED_AT = datetime(2026, 10, 21, 9, 0)


@tagged("post_install", "-at_install")
class TestLaboratoryFileLocks(LaboratoryFileLocksCase):
    def test_a_tester_locks_renews_and_unlocks_a_working_file(self):
        file = self.file_in("working")
        with freeze_time(LOCKED_AT):
            lock = self.lock_as(self.tester, file)
        self.assertRecordValues(
            lock,
            [
                {
                    "file_id": file.id,
                    "user_id": self.tester.id,
                    "device_id": self.computer.id,
                    "status": "active",
                    "expires_at": LOCKED_AT + timedelta(minutes=30),
                }
            ],
        )
        self.assertEqual((file.locked_by_id, file.locked_until), (self.tester, lock.expires_at))

        renewed_at = LOCKED_AT + timedelta(minutes=20)
        with freeze_time(renewed_at):
            self.assertEqual(file.with_user(self.tester)._renew_lock(), lock)
        self.assertEqual(lock.expires_at, renewed_at + timedelta(minutes=30))

        with freeze_time(renewed_at + timedelta(minutes=5)):
            file.with_user(self.tester)._unlock()
        self.assertRecordValues(
            lock, [{"status": "released", "released_at": renewed_at + timedelta(minutes=5), "released_by_id": False}]
        )
        file.invalidate_recordset()
        self.assertFalse(file.lock_id)

    def test_a_lock_expires_after_its_duration_unless_renewed(self):
        with freeze_time(LOCKED_AT):
            lock = self.lock_as(self.tester)
        with freeze_time(LOCKED_AT + timedelta(minutes=29)):
            self.assertEqual(self.file._lock_in_force(), lock)
            self.assertRefused(LOCKED, self.lock_as, self.member)
        with freeze_time(LOCKED_AT + timedelta(minutes=31)):
            self.assertFalse(self.file._lock_in_force())

        with freeze_time(LOCKED_AT + timedelta(minutes=20)):
            self.file.with_user(self.tester)._renew_lock()
        with freeze_time(LOCKED_AT + timedelta(minutes=45)):
            self.assertEqual(self.file._lock_in_force(), lock)

    def test_the_lock_duration_is_a_setting_of_at_least_a_minute(self):
        self.env["ir.config_parameter"].set_int(LABORATORY_FILE_LOCK_PARAMETER, 10)
        with freeze_time(LOCKED_AT):
            lock = self.lock_as(self.tester)

        self.assertEqual(lock.expires_at, LOCKED_AT + timedelta(minutes=10))
        with self.assertRaises(ValidationError):
            self.env[MODEL_RES_CONFIG_SETTINGS].create({"laboratory_file_lock_minutes": 0})

    def test_locking_a_file_again_renews_the_own_lock(self):
        with freeze_time(LOCKED_AT):
            lock = self.lock_as(self.tester)
        with freeze_time(LOCKED_AT + timedelta(minutes=10)):
            self.assertEqual(self.lock_as(self.tester), lock)

        self.assertEqual(lock.expires_at, LOCKED_AT + timedelta(minutes=40))
        self.assertEqual(self.file.lock_ids, lock)

    def test_working_result_and_uncategorized_files_that_are_not_office_documents_are_locked(self):
        for file in (self.file_in("working"), self.file_in("result"), self.file_in(False, "notes.txt"), self.file):
            with self.subTest(folder=file.folder_id.name):
                self.assertTrue(self.lock_as(self.member, file))

    def test_raw_data_office_documents_and_report_files_are_not_locked(self):
        files = (
            self.file_in(RAW_DATA, "run-01.csv"),
            self.file_in("report", "draft.txt"),
            self.file_in("working", "results.XLSX"),
            self.file_in(False, "method.docx"),
            self.file_in("result", "slides.pptx"),
        )
        for file in files:
            with self.subTest(path=file.path, category=file.folder_id.category):
                self.assertFalse(file._is_lockable())
                self.assertRefused(NOT_LOCKABLE, self.lock_as, self.member, file)
        self.assertFalse(self.env[MODEL_LABORATORY_FILE_LOCK].search([("file_id", "in", [f.id for f in files])]))

    def test_a_file_has_at_most_one_active_lock(self):
        lock = self.lock_as(self.tester)

        self.assertRefused(LOCKED, self.lock_as, self.member)
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.env[MODEL_LABORATORY_FILE_LOCK].create(
                {"file_id": self.file.id, "user_id": self.member.id, "expires_at": lock.expires_at}
            )

    def test_an_expired_lock_counts_as_none_before_the_job_expires_it(self):
        lock = self.lock_as(self.tester)
        self.pass_expiry(lock)
        expired_at = lock.expires_at

        taken = self.lock_as(self.member)

        self.assertRecordValues(lock, [{"status": "expired", "released_at": expired_at}])
        self.assertEqual((taken.user_id, taken.status), (self.member, "active"))

    def test_a_lock_that_expired_is_not_renewed_and_only_its_holder_renews_one(self):
        lock = self.lock_as(self.tester)

        self.assertRefused(LOCKED, self.file.with_user(self.member)._renew_lock)
        self.pass_expiry(lock)
        self.assertRefused(NOT_LOCKED, self.file.with_user(self.tester)._renew_lock)

    def test_unlocking_releases_only_the_own_lock_and_twice_does_no_harm(self):
        lock = self.lock_as(self.tester)

        self.file.with_user(self.member)._unlock()
        self.assertEqual(lock.status, "active")
        self.file.with_user(self.tester)._unlock()
        self.file.with_user(self.tester)._unlock()
        self.assertEqual(lock.status, "released")

    def test_locking_needs_writing_the_file_and_unlocking_needs_reading_it(self):
        self.assertRefused(NOT_FOUND, self.lock_as, self.outsider)
        self.assertRefused(PERMISSION_DENIED, self.lock_as, self.colleague)
        lock = self.lock_as(self.tester)
        self.folder.with_user(self.administrator).action_turn_off()

        self.assertRefused(FOLDER_DISABLED, self.file.with_user(self.tester)._renew_lock)
        self.file.with_user(self.tester)._unlock()
        self.assertEqual(lock.status, "released")
