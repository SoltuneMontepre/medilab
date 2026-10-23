from odoo.tests import tagged

from .laboratory_api_case import LaboratoryApiCase
from odoo.addons.sol_laboratory.constants.laboratory_files import RESTORED
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FILE_CHANGE


@tagged("post_install", "-at_install")
class TestLaboratoryFileChanges(LaboratoryApiCase):
    """The changes feed: what a computer reads of a folder after the last change it saw."""

    def setUp(self):
        super().setUp()
        self.key = self.signed_in_key(self.tester, "hplc-installation")
        self.path = f"/folders/{self.folder.id}/changes"

    def test_a_computer_reads_the_changes_to_current_versions_after_the_last_one_it_saw(self):
        run = self.file_of("HPLC/run-01.csv")
        first = self.save(run, "run 1")
        seen = self.api("GET", self.path, key=self.key).json()["changes"][-1]["id"]
        second = self.save(run, "run 2")
        self.save(run, "run 2, from version 1", base_version=first)
        restored = run._add_version(source=RESTORED, user=self.member, restored_from=first)
        other = self.save(self.file_of("HPLC/run-02.csv"), "run 2")

        changes = self.api("GET", f"{self.path}?after={seen}", key=self.key).json()

        # The conflict version is not current, so it is no change.
        self.assertEqual([change["version"]["id"] for change in changes["changes"]], [second.id, restored.id, other.id])
        self.assertEqual(changes["changes"][0]["file"], {"id": run.id, "path": "HPLC/run-01.csv"})
        self.assertIsNone(changes["next_after"])

    def test_changes_are_given_page_by_page_in_the_order_of_their_ids(self):
        for number in range(1, 6):
            self.save(self.file_of(f"HPLC/run-{number:02}.csv"), f"run {number}")
        ids = self.env[MODEL_LABORATORY_FILE_CHANGE].search([("folder_id", "=", self.folder.id)]).ids

        first = self.api("GET", f"{self.path}?limit=2", key=self.key).json()
        second = self.api("GET", f"{self.path}?after={first['next_after']}&limit=3", key=self.key).json()

        self.assertEqual([change["id"] for change in first["changes"] + second["changes"]], sorted(ids))
        self.assertIsNone(second["next_after"])
        self.assertEqual(self.api("GET", f"{self.path}?limit=101", key=self.key).status_code, 400)

    def test_no_path_takes_the_folders_feed_lock_before_the_files_row_lock(self):
        file = self.file_of("HPLC/run-01.csv")

        # Every save of the test suite goes through this check; a file whose row this transaction never locked fails it.
        with self.assertRaises(RuntimeError):
            file.sudo()._lock_feed()
        self.save(file, "run 1")
        self.assertEqual(file.current_version_id.number, 1)
