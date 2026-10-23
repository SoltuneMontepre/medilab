import re
from pathlib import Path

from odoo.modules.module import load_script
from odoo.tests import tagged
from odoo.tools.sql import column_exists

from .laboratory_files_case import LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.laboratory_files import VERIFIED

PRE_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.16.0" / "pre-migrate.py"
LOGGER = "laboratory_content_migration"


@tagged("post_install", "-at_install")
class TestLaboratoryContentMigration(LaboratoryFilesCase):
    """Versions as the database held them before stored content: each with a storage key of its own and no content.
    Two files share one content, and one file has two."""

    def setUp(self):
        super().setUp()
        first, second = self.file_of("HPLC/run-01.csv"), self.file_of("HPLC/run-02.csv")
        self.versions = (
            self.save(first, "run 1") | self.save(first, "run 1, again") | self.save(second, "run 1", user=self.member)
        )
        self.env.flush_all()
        cr = self.env.cr
        cr.execute("ALTER TABLE medilab_laboratory_file_version ADD COLUMN storage_key VARCHAR")
        cr.execute("UPDATE medilab_laboratory_file_version SET storage_key = 'demo/' || sha256")
        cr.execute("ALTER TABLE medilab_laboratory_file_version DROP COLUMN content_id")
        # Uploads came after this upgrade, so the database it upgrades has none.
        cr.execute("DELETE FROM medilab_laboratory_upload")
        cr.execute("DELETE FROM medilab_laboratory_content")
        cr.execute("SELECT COUNT(DISTINCT sha256), COUNT(*) FROM medilab_laboratory_file_version")
        [(self.contents, self.version_count)] = cr.fetchall()
        self.env.invalidate_all()

    def migrate(self):
        load_script(str(PRE_MIGRATE), LOGGER).migrate(self.env.cr, "20.0.1.15.0")
        self.env.invalidate_all()

    def migrated(self):
        """Each version's SHA-256 and size, and the key, state, SHA-256 and size of its content."""
        self.env.cr.execute(
            """
            SELECT version.id, version.sha256, version.size, content.object_key, content.state, content.sha256,
                   content.size
              FROM medilab_laboratory_file_version version
              JOIN medilab_laboratory_content content ON content.id = version.content_id
             WHERE version.id IN %s
             ORDER BY version.id
            """,
            [tuple(self.versions.ids)],
        )
        return self.env.cr.fetchall()

    def test_upgrade_records_the_content_of_each_sha256_as_verified_and_drops_the_storage_keys(self):
        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.migrate()

        rows = self.migrated()
        self.assertEqual(len(rows), 3)
        for _id, sha256, size, key, state, content_sha256, content_size in rows:
            self.assertEqual((state, content_sha256, content_size), (VERIFIED, sha256, size))
            self.assertTrue(re.fullmatch(r"[0-9a-f]{32}", key))
        self.assertEqual(rows[0][3], rows[2][3])
        self.assertNotEqual(rows[0][3], rows[1][3])
        self.assertFalse(column_exists(self.env.cr, "medilab_laboratory_file_version", "storage_key"))
        self.assertEqual(
            [record.getMessage() for record in logs.records],
            [
                (
                    f"Recorded {self.contents} laboratory file contents as verified for {self.version_count} versions; "
                    "their bytes are not in the bucket."
                )
            ],
        )

    def test_an_upgraded_database_is_left_as_it_is(self):
        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.migrate()
        self.assertEqual(
            [record.getMessage() for record in logs.records],
            [
                (
                    f"Recorded {self.contents} laboratory file contents as verified for {self.version_count} versions; "
                    "their bytes are not in the bucket."
                )
            ],
        )
        rows = self.migrated()

        with self.assertNoLogs(LOGGER, "WARNING"):
            self.migrate()

        self.assertEqual(self.migrated(), rows)
