import uuid

from odoo.tests import tagged

from .laboratory_files_case import stored_content
from .laboratory_files_concurrency_case import LaboratoryFilesConcurrencyCase
from odoo.addons.sol_laboratory.constants.laboratory_files import SYNCED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_CHANGE,
    MODEL_LABORATORY_FOLDER,
)


@tagged("post_install", "-at_install")
class TestLaboratoryFileChangeConcurrency(LaboratoryFilesConcurrencyCase):
    """Two saves of different files of one folder at once, in real database transactions: the second waits for the
    first's change to commit before it adds its own, so a computer reading the feed by id misses neither."""

    def setUp(self):
        super().setUp()
        self.committed(self.prepare)
        self.addCleanup(self.committed, self.remove)

    def prepare(self, env):
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_audit_entry")
        self.last_entry_id = env.cr.fetchone()[0]
        self.last_content_id = self.last_content(env)
        folder = env[MODEL_LABORATORY_FOLDER].create(
            {"name": f"Changes {uuid.uuid4().hex[:8]}", "owner_id": env.ref("base.user_admin").id}
        )
        self.folder_id = folder.id
        files = env[MODEL_LABORATORY_FILE]
        self.file_ids = [files._get_or_create(folder, path).id for path in ("run-01.csv", "run-02.csv")]

    def remove(self, env):
        # Files, versions, changes and content refuse deletion, so what these tests committed is removed with SQL.
        cr = env.cr
        cr.execute(
            "DELETE FROM medilab_audit_change WHERE entry_id IN (SELECT id FROM medilab_audit_entry WHERE id > %s)",
            [self.last_entry_id],
        )
        cr.execute("DELETE FROM medilab_audit_entry WHERE id > %s", [self.last_entry_id])
        cr.execute("DELETE FROM medilab_laboratory_file_change WHERE folder_id = %s", [self.folder_id])
        cr.execute(
            "UPDATE medilab_laboratory_file SET current_version_id = NULL WHERE folder_id = %s", [self.folder_id]
        )
        cr.execute("DELETE FROM medilab_laboratory_file_version WHERE file_id IN %s", [tuple(self.file_ids)])
        self.remove_contents(cr, self.last_content_id)
        cr.execute("DELETE FROM medilab_laboratory_file WHERE folder_id = %s", [self.folder_id])
        cr.execute("DELETE FROM medilab_laboratory_folder_member WHERE folder_id = %s", [self.folder_id])
        cr.execute("DELETE FROM medilab_laboratory_folder WHERE id = %s", [self.folder_id])

    def changes(self, env):
        return env[MODEL_LABORATORY_FILE_CHANGE].search([("folder_id", "=", self.folder_id)], order="id")

    def save(self, env, index):
        file = env[MODEL_LABORATORY_FILE].browse(self.file_ids[index])
        return file._add_version(
            content=stored_content(env, f"run {index + 1}"), source=SYNCED, user=env.ref("base.user_admin")
        )

    def test_a_change_of_a_folder_commits_before_any_change_of_a_higher_id(self):
        committed_before_second = []

        def second(env):
            version = self.save(env, 1)
            # By now this save holds the folder's feed lock, which it got once the first save committed.
            committed_before_second.append(self.committed(lambda other: self.changes(other).version_id.ids))
            return version

        attempts, second_id = self.race(lambda env: self.save(env, 0), second)

        def work(env):
            return [(change.file_id.id, change.version_id.id) for change in self.changes(env)]

        changes = self.committed(work)
        self.assertEqual(attempts, 1)
        self.assertEqual([file_id for file_id, _version_id in changes], self.file_ids)
        self.assertEqual(changes[1][1], second_id)
        self.assertEqual(committed_before_second, [[changes[0][1]]])
