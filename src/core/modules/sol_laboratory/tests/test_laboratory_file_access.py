from odoo.exceptions import AccessError
from odoo.tests import tagged

from .laboratory_files_case import LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    FILE_READ,
    FILE_WRITE,
    FOLDER_ARCHIVED,
    FOLDER_DISABLED,
    NOT_FOUND,
    PERMISSION_DENIED,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FILE, MODEL_LABORATORY_FILE_VERSION


@tagged("post_install", "-at_install")
class TestLaboratoryFileAccess(LaboratoryFilesCase):
    def setUp(self):
        super().setUp()
        self.file = self.file_of("HPLC/run-01.csv")
        self.version = self.save(self.file, "run 1")

    def test_members_read_the_files_and_versions_of_their_folders_and_nobody_else_does(self):
        files = self.env[MODEL_LABORATORY_FILE]
        versions = self.env[MODEL_LABORATORY_FILE_VERSION]

        for user in (self.tester, self.member):
            with self.subTest(user=user.login):
                self.assertEqual(files.with_user(user).search([]), self.file)
                self.assertEqual(versions.with_user(user).search([]), self.version)
        self.assertFalse(files.with_user(self.outsider).search([]))
        self.assertFalse(versions.with_user(self.outsider).search([]))
        with self.assertRaises(AccessError):
            files.with_user(self.colleague).search([])

    def test_members_read_and_write_the_files_of_their_folder(self):
        for user in (self.tester, self.member):
            for access in (FILE_READ, FILE_WRITE):
                with self.subTest(user=user.login, access=access):
                    self.file.with_user(user)._check_file_access(access)

    def test_a_person_who_is_not_a_member_gets_nothing_from_its_files(self):
        for access in (FILE_READ, FILE_WRITE):
            with self.subTest(access=access):
                self.assertRefused(NOT_FOUND, self.file.with_user(self.outsider)._check_file_access, access)
                self.assertRefused(NOT_FOUND, self.file.with_user(self.administrator)._check_file_access, access)
                self.assertRefused(PERMISSION_DENIED, self.file.with_user(self.colleague)._check_file_access, access)

    def test_the_files_of_a_turned_off_or_archived_folder_are_read_and_not_written(self):
        file = self.file.with_user(self.member)
        self.folder.with_user(self.administrator).action_turn_off()

        file._check_file_access(FILE_READ)
        self.assertRefused(FOLDER_DISABLED, file._check_file_access, FILE_WRITE)
        self.folder.with_user(self.administrator).action_turn_on()
        self.folder.with_user(self.administrator).action_archive_folder()
        file._check_file_access(FILE_READ)
        self.assertRefused(FOLDER_ARCHIVED, file._check_file_access, FILE_WRITE)
