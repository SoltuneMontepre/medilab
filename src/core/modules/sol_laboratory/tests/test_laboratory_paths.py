from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .laboratory_files_case import LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER, MODEL_LABORATORY_SYNC_RULE

PATHS = ("/home/lab/HPLC", "C:\\Data\\HPLC", "C:", "\\\\server\\share", "~/HPLC", "~", "..", ".", "HPLC/2026", " HPLC")


@tagged("post_install", "-at_install")
class TestLaboratoryPaths(LaboratoryFilesCase):
    def test_a_folder_is_named_never_given_a_path(self):
        folders = self.env[MODEL_LABORATORY_FOLDER]

        for path in PATHS:
            with self.subTest(path=path), self.assertRaises(ValidationError):
                folders.create({"name": path, "owner_id": self.tester.id})
        with self.assertRaises(ValidationError):
            self.folder.name = "/home/lab/HPLC"
        self.assertEqual(
            folders.create({"name": "Kết quả HPLC 2026", "owner_id": self.tester.id}).root, "Kết quả HPLC 2026"
        )

    def test_a_sync_rule_holds_a_name_prefix_pattern_or_extension_never_a_path(self):
        rules = self.env[MODEL_LABORATORY_SYNC_RULE]
        accepted = {"prefix": ("run-",), "glob": ("run-*.csv", "*"), "extension": ("csv", ".csv", "tar.gz")}
        refused = {
            "prefix": ("run/", "run-*", "C:\\run", *PATHS),
            "glob": ("HPLC/*.csv", "run-?.csv", "[ab].csv", *PATHS),
            "extension": ("*.csv", "c:sv", "csv/", "", "c s v"),
        }

        for kind, patterns in accepted.items():
            for pattern in patterns:
                with self.subTest(kind=kind, pattern=pattern):
                    # Removed again, as csv and .csv are one rule, which a folder has once.
                    rules.create({"folder_id": self.folder.id, "kind": kind, "pattern": pattern}).unlink()
        for kind, patterns in refused.items():
            for pattern in patterns:
                with self.subTest(kind=kind, pattern=pattern), self.assertRaises(ValidationError):
                    rules.create({"folder_id": self.folder.id, "kind": kind, "pattern": pattern})

    def test_an_extension_is_kept_without_its_dot_and_in_lowercase(self):
        rules = self.env[MODEL_LABORATORY_SYNC_RULE]
        # One folder each, as a folder has one rule of a kind and pattern.
        folders = self.folder | self.env[MODEL_LABORATORY_FOLDER].create(
            [{"name": name, "owner_id": self.tester.id} for name in ("AAS", "GC")]
        )
        created = rules.create(
            [
                {"folder_id": folder.id, "kind": "extension", "pattern": pattern}
                for folder, pattern in zip(folders, (".PDF", "Pdf", "pdf"), strict=True)
            ]
        )
        prefix = rules.create({"folder_id": self.folder.id, "kind": "prefix", "pattern": "XLSX"})

        self.assertEqual(created.mapped("pattern"), ["pdf", "pdf", "pdf"])
        created[0].pattern = ".Tar.GZ"
        self.assertEqual(created[0].pattern, "tar.gz")
        prefix.kind = "extension"
        self.assertEqual(prefix.pattern, "xlsx")
        (created[1] | prefix).write({"kind": "extension", "pattern": ".CSV"})
        self.assertEqual((created[1] | prefix).mapped("pattern"), ["csv", "csv"])
