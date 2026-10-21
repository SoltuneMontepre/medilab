from pathlib import Path

from odoo.modules.module import load_script
from odoo.tests import tagged

from .laboratory_files_case import LaboratoryFilesCase

PRE_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.15.0" / "pre-migrate.py"


@tagged("post_install", "-at_install")
class TestLaboratorySyncRuleMigration(LaboratoryFilesCase):
    def test_upgrade_keeps_the_oldest_of_rules_of_one_kind_and_pattern_and_logs_the_others(self):
        cr = self.env.cr
        # Rules made before the unique key, which the test drops for its own transaction only.
        cr.execute(
            "SELECT conname FROM pg_constraint WHERE conrelid = 'medilab_laboratory_sync_rule'::regclass AND contype = 'u'"
        )
        for (name,) in cr.fetchall():
            cr.execute(f'ALTER TABLE medilab_laboratory_sync_rule DROP CONSTRAINT "{name}"')
        rows = [("prefix", "run-", True, True), ("prefix", "run-", False, True), ("prefix", "run-", True, False)]
        rows.append(("extension", "csv", True, True))
        ids = []
        for kind, pattern, recursive, enabled in rows:
            cr.execute(
                """
                INSERT INTO medilab_laboratory_sync_rule (folder_id, kind, pattern, recursive, enabled)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
                """,
                [self.folder.id, kind, pattern, recursive, enabled],
            )
            [(rule_id,)] = cr.fetchall()
            ids.append(rule_id)

        with self.assertLogs(level="WARNING") as logged:
            load_script(str(PRE_MIGRATE), "pre_migrate").migrate(cr, "20.0.1.14.0")

        cr.execute("SELECT id FROM medilab_laboratory_sync_rule WHERE folder_id = %s ORDER BY id", [self.folder.id])
        self.assertEqual([rule_id for (rule_id,) in cr.fetchall()], [ids[0], ids[3]])
        self.assertEqual(len(logged.output), 2)
        self.assertIn(f"Deleted sync rule {ids[1]} of laboratory folder {self.folder.id}", logged.output[0])
        self.assertIn("include subfolders False, enabled True", logged.output[0])
        self.assertIn("include subfolders True, enabled False", logged.output[1])
