from types import SimpleNamespace

from odoo.exceptions import ConcurrencyError
from odoo.fields import Command
from odoo.http import retrying
from odoo.tests import tagged
from odoo.tools import mute_logger

from .laboratory_api_case import LaboratoryApiCase
from .laboratory_file_locks_case import LaboratoryFileLocksCase
from odoo.addons.sol_laboratory.constants.laboratory_editing import REPORT
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    FOLDER_ARCHIVED,
    FOLDER_DISABLED,
    LOCKED,
    MEMBER_ROLE,
    NOT_FOUND,
    NOT_LOCKABLE,
    NOT_LOCKED,
    PERMISSION_DENIED,
    RAW_DATA,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_ENTRY,
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_LOCK,
)
from odoo.addons.sol_laboratory.constants.xml_ids import LABORATORY_FILES_GROUP


@tagged("post_install", "-at_install")
class TestLaboratoryApiFileLocks(LaboratoryApiCase, LaboratoryFileLocksCase):
    """Locking, renewing and unlocking a file through the laboratory files API, from a computer's key."""

    def setUp(self):
        super().setUp()
        self.key = self.signed_in_key(self.tester, "tester-installation")
        self.members_key = self.signed_in_key(self.member, "members-installation")
        self.device = self.env[MODEL_LABORATORY_DEVICE].search([("client_uid", "=", "tester-installation")])

    def path(self, file=None, folder=None):
        file = file or self.file
        return f"/folders/{(folder or file.folder_id).id}/files/{file.id}/lock"

    def lock(self, file=None, key=None, headers=None):
        return self.api("POST", self.path(file), key=key or self.key, headers=headers)

    def active_locks(self, file=None):
        return self.env[MODEL_LABORATORY_FILE_LOCK].search(
            [("file_id", "=", (file or self.file).id), ("status", "=", "active")]
        )

    def test_locking_records_the_person_and_the_computer_of_the_key(self):
        other = self.env[MODEL_LABORATORY_DEVICE].search([("client_uid", "=", "members-installation")])

        lock = self.lock(headers={"X-Sync-Device-Id": str(other.id)}).json()["lock"]

        self.assertEqual(
            {key: lock[key] for key in ("file_id", "user", "device_id", "status")},
            {
                "file_id": self.file.id,
                "user": {"id": self.tester.id, "name": self.tester.name},
                "device_id": self.device.id,
                "status": "active",
            },
        )
        self.assertEqual(self.active_locks().device_id, self.device)

    def test_locking_again_renews_the_persons_lock(self):
        first = self.lock().json()["lock"]
        again = self.lock().json()["lock"]

        self.assertEqual(again["id"], first["id"])
        self.assertEqual(len(self.active_locks()), 1)

    def test_a_file_someone_else_holds_is_not_locked_or_renewed_meanwhile(self):
        self.lock()

        warning = self.timestamped_http_warning(f"{self.tester.display_name} has locked {self.file.path} until ")
        with self.expected_http_warnings(warning, warning):
            self.assertApiRefused(LOCKED, self.lock(key=self.members_key))
            self.assertApiRefused(LOCKED, self.api("POST", f"{self.path()}/renew", key=self.members_key))
        self.assertEqual(self.active_locks().user_id, self.tester)

    def test_the_holder_renews_a_lock_in_force_and_not_one_that_expired(self):
        self.lock()

        renewed = self.api("POST", f"{self.path()}/renew", key=self.key)
        self.assertEqual(renewed.json()["lock"]["id"], self.active_locks().id)

        self.pass_expiry(self.active_locks())
        with self.expected_http_warnings("You no longer hold a lock on HPLC/calibration.csv; lock it again."):
            self.assertApiRefused(NOT_LOCKED, self.api("POST", f"{self.path()}/renew", key=self.key))

    def test_unlocking_twice_has_the_effect_of_once(self):
        self.lock()

        self.assertEqual(self.api("DELETE", self.path(), key=self.key).status_code, 204)
        self.assertEqual(self.api("DELETE", self.path(), key=self.key).status_code, 204)
        self.assertFalse(self.active_locks())
        self.assertEqual(self.lock(key=self.members_key).status_code, 200)

    def test_only_files_that_are_neither_raw_data_nor_office_documents_nor_reports_are_locked(self):
        for file in (self.file_in(RAW_DATA), self.file_in(REPORT), self.file_in("working", "report.docx")):
            with self.subTest(file=file.path, category=file.folder_id.category):
                with self.expected_http_warnings("Raw data, Office documents and report files are not locked."):
                    self.assertApiRefused(NOT_LOCKABLE, self.lock(file))

    def test_a_turned_off_folder_refuses_locks_and_its_holder_still_unlocks(self):
        self.lock()
        self.file.folder_id.with_user(self.administrator).action_turn_off()

        with self.expected_http_warnings("This laboratory folder is turned off: its files are read, not changed."):
            self.assertApiRefused(FOLDER_DISABLED, self.lock())
        self.assertEqual(self.api("DELETE", self.path(), key=self.key).status_code, 204)
        self.assertFalse(self.active_locks())

    def test_an_archived_folder_refuses_locks(self):
        self.file.folder_id.with_user(self.administrator).action_archive_folder()

        with self.expected_http_warnings("This laboratory folder is archived: it is read, not changed."):
            self.assertApiRefused(FOLDER_ARCHIVED, self.lock())

    def test_a_file_the_person_may_not_reach_is_not_found(self):
        outsiders_key = self.signed_in_key(self.outsider, "outsiders-installation")
        other_folder = self.file_in("working", "other.csv").folder_id
        unseen = self.file_in("working", "unseen.csv")
        unseen.folder_id.member_ids = [Command.create({"user_id": self.outsider.id, "role": MEMBER_ROLE})]
        no_file = f"/folders/{self.file.folder_id.id}/files/0/lock"

        for reason, path, key in (
            ("not a member", self.path(), outsiders_key),
            ("a file of another folder", self.path(folder=other_folder), self.key),
            ("no file", no_file, self.key),
            ("a sample the person does not see", self.path(unseen), outsiders_key),
        ):
            message = (
                "This laboratory folder does not exist or you do not have access to it."
                if reason in ("not a member", "a sample the person does not see")
                else "This file does not exist in the folder."
            )
            with self.subTest(reason), self.expected_http_warnings(message, message, message):
                self.assertApiRefused(NOT_FOUND, self.api("POST", path, key=key))
                self.assertApiRefused(NOT_FOUND, self.api("DELETE", path, key=key))
                self.assertApiRefused(NOT_FOUND, self.api("POST", f"{path}/renew", key=key))

    def test_a_person_without_the_laboratory_files_permission_locks_nothing(self):
        self.tester.write({"group_ids": [Command.unlink(self.env.ref(LABORATORY_FILES_GROUP).id)]})

        with self.expected_http_warnings("You do not have the laboratory files permission."):
            self.assertApiRefused(PERMISSION_DENIED, self.lock())
        self.assertFalse(self.active_locks())

    def test_a_lock_run_again_by_odoos_retrying_locks_once(self):
        self.patch(retrying, "random", SimpleNamespace(uniform=lambda _low, _high: 0))
        files = type(self.env[MODEL_LABORATORY_FILE])
        lock = files._lock
        runs = []

        def failing_once(file, device=None):
            runs.append(1)
            if len(runs) == 1:
                raise ConcurrencyError("A concurrent request changed the same file.")
            return lock(file, device)

        self.patch(files, "_lock", failing_once)
        with mute_logger("odoo.http"):
            response = self.lock()

        locks = self.env[MODEL_LABORATORY_FILE_LOCK].search([("file_id", "=", self.file.id)])
        entries = self.env[MODEL_AUDIT_ENTRY].search(
            [
                ("document_model", "=", MODEL_LABORATORY_FILE_LOCK),
                ("document_id", "in", locks.ids),
                ("action", "=", "create"),
            ]
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(runs), 2)
        self.assertEqual(len(self.active_locks()), 1)
        self.assertEqual((len(locks), len(entries)), (1, 1))
