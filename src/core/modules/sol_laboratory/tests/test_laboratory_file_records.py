import unicodedata

from psycopg2 import IntegrityError

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .laboratory_files_case import LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FOLDER,
    MODEL_LABORATORY_SYNC_RULE,
)

PATHS = ("/HPLC/run.csv", "C:\\HPLC\\run.csv", "HPLC/../run.csv", "~/run.csv", "HPLC//run.csv", "HPLC/", " run.csv")
RESULTS = "Kết quả HPLC.xlsx"


@tagged("post_install", "-at_install")
class TestLaboratoryFileRecords(LaboratoryFilesCase):
    def create_file(self, path, folder=None):
        return self.env[MODEL_LABORATORY_FILE].create({"folder_id": (folder or self.folder).id, "path": path})

    def test_a_path_is_relative_to_its_folder(self):
        self.assertEqual(self.create_file("HPLC/2026/run-01.csv").path, "HPLC/2026/run-01.csv")
        for path in PATHS:
            with self.subTest(path=path), self.assertRaises(ValidationError):
                self.create_file(path)

    def test_paths_that_differ_only_in_letter_case_are_one_file(self):
        file = self.create_file("HPLC/Run-01.csv")

        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.create_file("hplc/run-01.CSV")
        self.assertEqual(file.path, "HPLC/Run-01.csv")

    def test_another_folder_may_hold_the_same_path(self):
        other = self.env[MODEL_LABORATORY_FOLDER].create({"name": "AAS", "owner_id": self.tester.id})

        self.create_file("run-01.csv")
        self.assertEqual(self.create_file("run-01.csv", other).folder_id, other)

    def test_a_path_is_kept_in_one_unicode_form(self):
        file = self.create_file(unicodedata.normalize("NFD", RESULTS))

        self.assertEqual(file.path, RESULTS)
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.create_file(RESULTS)

    def test_a_file_keeps_its_folder_and_its_path(self):
        file = self.create_file("run-01.csv")
        other = self.env[MODEL_LABORATORY_FOLDER].create({"name": "AAS", "owner_id": self.tester.id})

        for values in ({"path": "run-02.csv"}, {"folder_id": other.id}):
            with self.subTest(values=values), self.assertRaises(UserError):
                file.write(values)

    def test_a_file_is_never_deleted(self):
        file = self.create_file("run-01.csv")

        with self.assertRaises(UserError):
            file.unlink()

    def test_folder_names_and_rule_patterns_are_kept_in_one_unicode_form(self):
        folder = self.env[MODEL_LABORATORY_FOLDER].create(
            {"name": unicodedata.normalize("NFD", "Kết quả"), "owner_id": self.tester.id}
        )
        rule = self.env[MODEL_LABORATORY_SYNC_RULE].create(
            {"folder_id": folder.id, "kind": "prefix", "pattern": unicodedata.normalize("NFD", "kết-quả-")}
        )
        folder.name = unicodedata.normalize("NFD", "Kết quả 2026")

        self.assertEqual((folder.name, folder.root, rule.pattern), ("Kết quả 2026", "Kết quả", "kết-quả-"))
