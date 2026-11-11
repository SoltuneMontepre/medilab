from odoo.tests import tagged

from .laboratory_files_concurrency_case import LaboratoryFilesConcurrencyCase
from odoo.addons.sol_laboratory.constants.laboratory_files import RAW_DATA, RESULT
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER, MODEL_SAMPLE


@tagged("post_install", "-at_install")
class TestLaboratorySampleFolderConcurrency(LaboratoryFilesConcurrencyCase):
    """Two real database transactions creating the folders of one sample at once, the second one through Odoo's request
    retrying."""

    def setUp(self):
        super().setUp()
        self.ids = self.committed(self.prepare)
        self.addCleanup(self.committed, self.remove)

    def prepare(self, env):
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_audit_entry")
        self.last_entry_id = env.cr.fetchone()[0]
        return self.create_sample(env)

    def remove(self, env):
        # Folders, samples and requests refuse deletion, so the data these tests committed is removed with SQL.
        cr = env.cr
        cr.execute(
            "DELETE FROM medilab_audit_change WHERE entry_id IN (SELECT id FROM medilab_audit_entry WHERE id > %s)",
            [self.last_entry_id],
        )
        cr.execute("DELETE FROM medilab_audit_entry WHERE id > %s", [self.last_entry_id])
        self.remove_sample(cr, self.ids)

    def create_folders(self, env):
        folders = env[MODEL_SAMPLE].browse(self.ids["sample"])._create_laboratory_folders(env.ref("base.user_admin"))
        return env[MODEL_SAMPLE].browse(self.ids["sample"]) if not folders else folders[:1]

    def test_two_creations_of_a_samples_folders_at_once_make_one_folder_of_each_category(self):
        attempts, _second = self.race(self.create_folders, self.create_folders)

        def work(env):
            folders = env[MODEL_LABORATORY_FOLDER].search([("sample_id", "=", self.ids["sample"])])
            return sorted(folders.mapped("category"))

        self.assertEqual(attempts, 2)
        self.assertEqual(self.committed(work), sorted([RAW_DATA, RESULT]))
