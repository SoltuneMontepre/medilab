import unicodedata
from pathlib import Path

from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.modules.module import load_script
from odoo.tests import tagged
from odoo.tools import mute_logger

from .laboratory_files_case import LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_SYNC_RULE

PRE_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.15.0" / "pre-migrate.py"
# A Vietnamese prefix typed in decomposed Unicode, as some computers send it.
DECOMPOSED_PREFIX = unicodedata.normalize("NFD", "Kết-quả-")


@tagged("post_install", "-at_install")
class TestLaboratorySyncRuleMigration(LaboratoryFilesCase):
    def setUp(self):
        super().setUp()
        # Rules are made as before the unique key, which the test drops for its own transaction only and adds back once
        # the upgrade ran.
        cr = self.env.cr
        cr.execute(
            """
            SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
             WHERE conrelid = 'medilab_laboratory_sync_rule'::regclass AND contype = 'u'
            """
        )
        self.unique_keys = cr.fetchall()
        for name, _definition in self.unique_keys:
            cr.execute(f'ALTER TABLE medilab_laboratory_sync_rule DROP CONSTRAINT "{name}"')

    def insert_rules(self, *rows):
        ids = []
        for kind, pattern, recursive, enabled in rows:
            self.env.cr.execute(
                """
                INSERT INTO medilab_laboratory_sync_rule (folder_id, kind, pattern, recursive, enabled)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
                """,
                [self.folder.id, kind, pattern, recursive, enabled],
            )
            [(rule_id,)] = self.env.cr.fetchall()
            ids.append(rule_id)
        return ids

    def upgrade(self):
        load_script(str(PRE_MIGRATE), "pre_migrate").migrate(self.env.cr, "20.0.1.14.0")

    def stored_rules(self):
        self.env.cr.execute(
            "SELECT id, kind, pattern, recursive, enabled FROM medilab_laboratory_sync_rule WHERE folder_id = %s "
            "ORDER BY id",
            [self.folder.id],
        )
        return self.env.cr.fetchall()

    def add_unique_keys(self):
        for name, definition in self.unique_keys:
            self.env.cr.execute(f'ALTER TABLE medilab_laboratory_sync_rule ADD CONSTRAINT "{name}" {definition}')

    def test_upgrade_keeps_the_oldest_of_rules_that_are_one_rule_with_the_same_flags_and_logs_the_others(self):
        ids = self.insert_rules(
            ("prefix", "run-", False, True),
            ("prefix", "run-", False, True),
            ("prefix", DECOMPOSED_PREFIX, True, True),
            ("prefix", "Kết-quả-", True, True),
            ("extension", "CSV", True, True),
            ("extension", ".csv", True, True),
            ("glob", "run-*.csv", True, True),
        )

        with self.assertLogs(level="WARNING") as logged:
            self.upgrade()

        self.assertEqual(
            self.stored_rules(),
            [
                (ids[0], "prefix", "run-", False, True),
                (ids[2], "prefix", "Kết-quả-", True, True),
                (ids[4], "extension", "csv", True, True),
                (ids[6], "glob", "run-*.csv", True, True),
            ],
        )
        self.assertEqual(len(logged.output), 3)
        self.assertIn(f"Deleted sync rule {ids[1]} of laboratory folder {self.folder.id}", logged.output[0])
        self.assertIn("a second prefix rule 'run-': include subfolders False, enabled True", logged.output[0])
        self.assertIn(f"Deleted sync rule {ids[3]} ", logged.output[1])
        self.assertIn(f"Deleted sync rule {ids[5]} ", logged.output[2])
        self.assertIn("a second extension rule 'csv'", logged.output[2])

        self.add_unique_keys()
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env[MODEL_LABORATORY_SYNC_RULE].create(
                {"folder_id": self.folder.id, "kind": "extension", "pattern": ".CSV"}
            )

    def test_upgrade_with_rules_that_are_one_rule_with_other_flags_is_refused_and_changes_no_rule(self):
        ids = self.insert_rules(
            ("prefix", "run-", True, True),
            ("prefix", "run-", True, True),
            ("extension", "csv", True, True),
            ("extension", "CSV", False, True),
            ("glob", "*.pdf", True, True),
            ("glob", "*.pdf", True, False),
        )
        rules = self.stored_rules()

        with self.assertRaises(UserError) as refused:
            self.upgrade()

        self.assertEqual(self.stored_rules(), rules)
        message = str(refused.exception)
        self.assertIn("then upgrade again", message)
        self.assertNotIn(f"rule {ids[0]} ", message)
        self.assertIn(
            f"Folder {self.folder.id} 'HPLC', extension 'csv': rule {ids[2]} (include subfolders True, enabled True), "
            f"rule {ids[3]} (include subfolders False, enabled True)",
            message,
        )
        self.assertIn(
            f"Folder {self.folder.id} 'HPLC', glob '*.pdf': rule {ids[4]} (include subfolders True, enabled True), "
            f"rule {ids[5]} (include subfolders True, enabled False)",
            message,
        )

    def test_upgrade_run_again_once_an_administrator_resolved_the_rules_succeeds_once(self):
        ids = self.insert_rules(
            ("prefix", "run-", True, True),
            ("prefix", "run-", True, False),
            ("extension", "csv", True, True),
            ("extension", "csv", True, True),
        )
        with self.assertRaises(UserError):
            self.upgrade()
        self.env.cr.execute("DELETE FROM medilab_laboratory_sync_rule WHERE id = %s", [ids[1]])

        with self.assertLogs(level="WARNING") as logged:
            self.upgrade()
        with self.assertNoLogs(level="WARNING"):
            self.upgrade()

        self.assertEqual(
            self.stored_rules(), [(ids[0], "prefix", "run-", True, True), (ids[2], "extension", "csv", True, True)]
        )
        self.assertEqual(len(logged.output), 1)
        self.assertIn(f"Deleted sync rule {ids[3]} ", logged.output[0])
        self.add_unique_keys()
