from odoo.exceptions import UserError
from odoo.tests import tagged

from .laboratory_files_case import LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    CONFLICT,
    EDITED_ONLINE,
    FOLDER_ARCHIVED,
    FOLDER_DISABLED,
    RESTORED,
    SYNCED,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_DEVICE, MODEL_LABORATORY_FILE_CHANGE


@tagged("post_install", "-at_install")
class TestLaboratoryFileVersions(LaboratoryFilesCase):
    def setUp(self):
        super().setUp()
        self.file = self.file_of("HPLC/run-01.csv")

    def changes(self):
        return self.env[MODEL_LABORATORY_FILE_CHANGE].search([("file_id", "=", self.file.id)])

    def save_many(self, count):
        return [self.save(self.file, f"run {number}") for number in range(1, count + 1)]

    def test_saving_a_file_adds_a_version_with_the_person_the_computer_the_size_and_the_hash(self):
        computer = self.env[MODEL_LABORATORY_DEVICE].create(
            {"user_id": self.member.id, "client_uid": "hplc-installation", "name": "PC-HPLC-01", "platform": "windows"}
        )

        version = self.save(self.file, "run 1", user=self.member, device=computer)

        self.assertEqual(
            (version.number, version.user_id, version.device_id, version.size, version.sha256, version.source),
            (1, self.member, computer, len("run 1"), self.sha("run 1"), SYNCED),
        )
        self.assertEqual(self.file.current_version_id, version)
        self.assertEqual(self.changes().version_id, version)

    def test_each_version_is_numbered_after_the_last_and_names_the_one_it_followed(self):
        first, second, third = self.save_many(3)

        self.assertEqual((first.number, second.number, third.number), (1, 2, 3))
        self.assertEqual((second.parent_version_id, third.parent_version_id), (first, second))
        self.assertEqual(self.changes().version_id, first | second | third)

    def test_a_save_from_a_version_that_is_no_longer_current_is_kept_as_a_conflict(self):
        versions = self.save_many(11)

        conflict = self.save(self.file, "edited from 10", base_version=versions[9])

        self.assertEqual((conflict.number, conflict.source, conflict.parent_version_id), (12, CONFLICT, versions[10]))
        self.assertEqual(self.file.current_version_id, versions[10])
        self.assertNotIn(conflict, self.changes().version_id)

    def test_a_save_from_the_current_version_becomes_current(self):
        first = self.save(self.file, "run 1")

        edited = self.save(self.file, "edited online", source=EDITED_ONLINE, base_version=first)

        self.assertEqual((edited.source, self.file.current_version_id), (EDITED_ONLINE, edited))

    def test_the_content_the_file_already_has_adds_nothing(self):
        first, second = self.save_many(2)

        for base_version in (second, first, None):
            with self.subTest(base_version=base_version):
                self.assertEqual(self.save(self.file, "run 2", base_version=base_version), second)
        self.assertEqual(len(self.file.version_ids), 2)

    def test_restoring_version_3_of_5_adds_version_6_with_its_content(self):
        versions = self.save_many(5)
        third = versions[2]

        restored = self.file._add_version(
            sha256=third.sha256,
            size=third.size,
            storage_key=third.storage_key,
            source=RESTORED,
            user=self.member,
            restored_from=third,
        )

        self.assertEqual((restored.number, restored.restored_from_id, restored.sha256), (6, third, third.sha256))
        self.assertEqual(self.file.current_version_id, restored)
        again = self.file._add_version(
            sha256=third.sha256,
            size=third.size,
            storage_key=third.storage_key,
            source=RESTORED,
            user=self.member,
            restored_from=third,
        )
        self.assertEqual(again.number, 7)

    def test_the_current_version_never_moves_back_to_an_older_one(self):
        first, second = self.save_many(2)

        with self.assertRaises(UserError):
            self.file._make_current(first)
        with self.assertRaises(UserError):
            self.file.current_version_id = first
        self.assertEqual(self.file.current_version_id, second)

    def test_a_turned_off_or_archived_folder_takes_no_new_version_whatever_the_rights(self):
        self.save(self.file, "run 1")
        self.folder.enabled = False

        self.assertRefused(FOLDER_DISABLED, lambda: self.save(self.file.sudo(), "run 2"))
        self.folder.enabled = True
        self.folder.with_user(self.administrator).action_archive_folder()
        self.assertRefused(FOLDER_ARCHIVED, lambda: self.save(self.file.sudo(), "run 2"))
        self.assertEqual(len(self.file.version_ids), 1)

    def test_a_save_that_is_rolled_back_leaves_no_gap_in_the_numbers(self):
        self.save(self.file, "run 1")
        with self.assertRaises(RuntimeError), self.env.cr.savepoint():
            self.save(self.file, "run 2")
            raise RuntimeError

        self.file.invalidate_recordset()
        self.assertEqual(self.save(self.file, "run 2 again").number, 2)

    def test_a_path_in_another_letter_case_is_the_same_file(self):
        self.assertEqual(self.file_of("hplc/RUN-01.CSV"), self.file)
        self.assertEqual(self.file.path, "HPLC/run-01.csv")
