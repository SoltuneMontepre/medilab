from odoo.fields import Command
from odoo.tests import tagged

from .laboratory_files_case import LaboratoryFilesCase
from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    FILE_READ,
    FILE_WRITE,
    FOLDER_ADMINISTER,
    FOLDER_ARCHIVED,
    FOLDER_READ,
    FOLDER_SAMPLE_CLOSED,
    FOLDER_SHARE,
    NOT_FOUND,
    RESULT,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER
from odoo.addons.sol_laboratory.constants.xml_ids import FOLDER_ADMINISTRATION_GROUP
from odoo.addons.sol_laboratory.services.record_id import persisted_id

SAMPLE_READER_GROUP = "sol_laboratory.group_permission_sample_read_all"


@tagged("post_install", "-at_install")
class TestLaboratorySampleFolderAccess(LaboratoryFilesCase, RequestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.raw_data = cls.env[MODEL_LABORATORY_FOLDER].create(
            {"name": "Raw data", "owner_id": cls.tester.id, "sample_id": cls.sample.id, "category": "raw"}
        )
        cls.folder_administrator = cls.create_user("lab.folders", FOLDER_ADMINISTRATION_GROUP)

    def test_a_member_who_cannot_see_the_sample_gets_nothing_from_its_folder(self):
        self.assertRefused(NOT_FOUND, self.raw_data.with_user(self.tester)._check_folder_access, FOLDER_READ)

    def test_a_member_who_can_see_the_sample_reads_its_folder(self):
        self.tester.group_ids = [Command.link(persisted_id(self.env.ref(SAMPLE_READER_GROUP)))]

        self.raw_data.with_user(self.tester)._check_folder_access(FOLDER_READ)

    def test_the_files_of_a_sample_folder_need_the_sample_too(self):
        file = self.file_of("HPLC/run-01.csv", self.raw_data)

        self.assertRefused(NOT_FOUND, file.with_user(self.tester)._check_file_access, FILE_READ)
        self.tester.group_ids = [Command.link(persisted_id(self.env.ref(SAMPLE_READER_GROUP)))]
        file.with_user(self.tester)._check_file_access(FILE_READ)
        self.assertTrue(file._is_raw_data())

    def test_the_files_of_a_completed_or_cancelled_sample_folder_are_read_only(self):
        for status in ("completed", "cancelled"):
            with self.subTest(status=status):
                folder = self.folder_of_category(RESULT, name=f"{status.title()} results")
                file = self.file_of("HPLC/run-01.xlsx", folder)
                lockable = self.file_of("HPLC/notes.csv", folder)
                self.save(file, "results")
                self.save(lockable, "notes")
                lockable.with_user(self.tester)._lock()
                folder.sample_id.status = status

                file.with_user(self.tester)._check_file_access(FILE_READ)
                self.assertRefused(FOLDER_SAMPLE_CLOSED, file.with_user(self.tester)._check_file_access, FILE_WRITE)
                self.assertRefused(FOLDER_SAMPLE_CLOSED, self.save, file, "new results")
                self.assertEqual(len(file.version_ids), 1)
                self.assertEqual(file.with_user(self.tester).action_open()["view_mode"], "form")
                self.assertRefused(FOLDER_SAMPLE_CLOSED, lockable.with_user(self.tester)._lock)
                lockable.with_user(self.tester)._unlock()

    def test_a_folder_administrator_who_cannot_see_the_sample_neither_shares_nor_administers_its_folder(self):
        archived = self.env[MODEL_LABORATORY_FOLDER].create(
            {"name": "Results", "owner_id": self.tester.id, "sample_id": self.sample.id, "category": RESULT}
        )
        archived.archived_at = "2026-10-20 08:00:00"
        raw_data = self.raw_data.with_user(self.folder_administrator)

        for access in (FOLDER_SHARE, FOLDER_ADMINISTER):
            with self.subTest(access=access):
                self.assertRefused(NOT_FOUND, raw_data._check_folder_access, access)
                self.assertRefused(
                    NOT_FOUND, archived.with_user(self.folder_administrator)._check_folder_access, access
                )
        self.assertRefused(NOT_FOUND, raw_data.action_turn_off)

        self.folder_administrator.group_ids = [Command.link(persisted_id(self.env.ref(SAMPLE_READER_GROUP)))]
        for access in (FOLDER_SHARE, FOLDER_ADMINISTER):
            with self.subTest(access=access, sees_sample=True):
                raw_data._check_folder_access(access)
        self.assertRefused(
            FOLDER_ARCHIVED, archived.with_user(self.folder_administrator)._check_folder_access, FOLDER_SHARE
        )
