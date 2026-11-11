from pathlib import Path

from odoo.modules.module import load_script
from odoo.tests import tagged
from odoo.tools.sql import drop_constraint

from .laboratory_files_case import LaboratoryFilesCase
from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.laboratory_files import RAW_DATA, RESULT
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER

PRE_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.13.0" / "pre-migrate.py"
LOGGER = "laboratory_folder_category_migration"
CHECK = "medilab_laboratory_folder_category_of_sample"


@tagged("post_install", "-at_install")
class TestLaboratoryFolderCategoryMigration(LaboratoryFilesCase, RequestCase):
    """The HPLC raw-data folder, which holds a run file, and the report drafts folder, both of no sample with a
    category as the database accepted them before the check, next to the lead sample's results folder."""

    def setUp(self):
        super().setUp()
        folders = self.env[MODEL_LABORATORY_FOLDER]
        self.raw_data = folders.create({"name": "HPLC raw data", "owner_id": self.tester.id})
        self.save(self.file_of("run-01.csv", self.raw_data), "run 1")
        self.report_drafts = folders.create({"name": "Report drafts", "owner_id": self.tester.id})
        self.results = folders.create(
            {"name": "Results", "owner_id": self.tester.id, "sample_id": self.sample.id, "category": RESULT}
        )
        self.env.flush_all()
        drop_constraint(self.env.cr, "medilab_laboratory_folder", CHECK)
        self.env.cr.execute(
            "UPDATE medilab_laboratory_folder SET category = %s WHERE id = %s", [RAW_DATA, self.raw_data.id]
        )
        self.env.cr.execute(
            "UPDATE medilab_laboratory_folder SET category = 'report' WHERE id = %s", [self.report_drafts.id]
        )
        self.env.invalidate_all()

    def migrate(self):
        load_script(str(PRE_MIGRATE), LOGGER).migrate(self.env.cr, "20.0.1.12.0")
        self.env.invalidate_all()

    def test_upgrade_clears_the_category_of_folders_of_no_sample_and_logs_each(self):
        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.migrate()

        self.assertFalse(self.raw_data.category)
        self.assertFalse(self.report_drafts.category)
        self.assertEqual(self.results.category, RESULT)
        self.assertFalse(self.folder.category)
        cleared = "Cleared the category {} of laboratory folder {} ({}), which has no sample. Files in it: {}."
        self.assertEqual(
            [record.getMessage() for record in logs.records],
            [
                cleared.format(RAW_DATA, self.raw_data.id, "HPLC raw data", 1),
                cleared.format("report", self.report_drafts.id, "Report drafts", 0),
            ],
        )

    def test_upgrading_again_changes_nothing(self):
        with self.assertLogs(LOGGER, "WARNING"):
            self.migrate()

        with self.assertNoLogs(LOGGER, "WARNING"):
            self.migrate()
        self.assertEqual(self.results.category, RESULT)

    def test_the_check_is_added_once_the_upgrade_cleared_the_categories(self):
        folders = self.env[MODEL_LABORATORY_FOLDER]
        with self.assertLogs(LOGGER, "WARNING"):
            self.migrate()

        folders._add_sql_constraints()

        self.assertTrue(folders._table_objects[CHECK].matches_database(folders))
