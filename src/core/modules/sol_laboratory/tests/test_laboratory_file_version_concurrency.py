import uuid

from odoo.tests import tagged

from .laboratory_files_case import stored_content
from .laboratory_files_concurrency_case import LaboratoryFilesConcurrencyCase
from odoo.addons.sol_laboratory.constants.laboratory_files import CONFLICT, EDITED_ONLINE, RESTORED, SYNCED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_LABORATORY_FOLDER,
)


def save(file, content, source=SYNCED, **values):
    return file._add_version(
        content=stored_content(file.env, content), source=source, user=file.env.ref("base.user_admin"), **values
    )


@tagged("post_install", "-at_install")
class TestLaboratoryFileVersionConcurrency(LaboratoryFilesConcurrencyCase):
    """Two real database transactions saving the same file at once, the second one through Odoo's request retrying."""

    def setUp(self):
        super().setUp()
        self.folder_id, self.file_id, self.first_id = self.committed(self.prepare)
        self.addCleanup(self.committed, self.remove)

    def prepare(self, env):
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_audit_entry")
        self.last_entry_id = env.cr.fetchone()[0]
        self.last_content_id = self.last_content(env)
        folder = env[MODEL_LABORATORY_FOLDER].create(
            {"name": f"Concurrency {uuid.uuid4().hex[:8]}", "owner_id": env.ref("base.user_admin").id}
        )
        file = env[MODEL_LABORATORY_FILE]._get_or_create(folder, "run-01.csv")
        return folder.id, file.id, save(file, "run 1").id

    def remove(self, env):
        # Files, versions and changes refuse deletion, so the data these tests committed is removed with SQL.
        cr = env.cr
        cr.execute(
            "DELETE FROM medilab_audit_change WHERE entry_id IN "
            "(SELECT id FROM medilab_audit_entry WHERE id > %s AND document_model LIKE 'medilab.laboratory.%%')",
            [self.last_entry_id],
        )
        cr.execute(
            "DELETE FROM medilab_audit_entry WHERE id > %s AND document_model LIKE 'medilab.laboratory.%%'",
            [self.last_entry_id],
        )
        cr.execute("DELETE FROM medilab_laboratory_file_change WHERE folder_id = %s", [self.folder_id])
        cr.execute(
            "UPDATE medilab_laboratory_file SET current_version_id = NULL WHERE folder_id = %s", [self.folder_id]
        )
        cr.execute(
            "DELETE FROM medilab_laboratory_file_version WHERE file_id IN "
            "(SELECT id FROM medilab_laboratory_file WHERE folder_id = %s)",
            [self.folder_id],
        )
        self.remove_contents(cr, self.last_content_id)
        cr.execute("DELETE FROM medilab_laboratory_file WHERE folder_id = %s", [self.folder_id])
        cr.execute("DELETE FROM medilab_laboratory_folder_member WHERE folder_id = %s", [self.folder_id])
        cr.execute("DELETE FROM medilab_laboratory_folder WHERE id = %s", [self.folder_id])

    def versions(self):
        def work(env):
            file = env[MODEL_LABORATORY_FILE].browse(self.file_id)
            return [(version.number, version.source) for version in file.version_ids.sorted("number")], (
                file.current_version_id.number
            )

        return self.committed(work)

    def file(self, env):
        return env[MODEL_LABORATORY_FILE].browse(self.file_id)

    def first_version(self, env):
        return env[MODEL_LABORATORY_FILE_VERSION].browse(self.first_id)

    def test_an_upload_and_an_online_save_at_once_get_the_next_two_numbers(self):
        # The race mutes the logger Odoo's retrying writes to, so a race that runs again logs nothing.
        with self.assertNoLogs("odoo.http", "INFO"):
            attempts, _second = self.race(
                lambda env: save(self.file(env), "uploaded", base_version=self.first_version(env)),
                lambda env: save(self.file(env), "edited", EDITED_ONLINE, base_version=self.first_version(env)),
            )

        self.assertEqual(attempts, 2)
        # The online save was made from version 1, which was no longer current once the upload committed.
        self.assertEqual(self.versions(), ([(1, SYNCED), (2, SYNCED), (3, CONFLICT)], 2))

    def test_an_upload_and_a_restore_at_once_get_the_next_two_numbers(self):
        def restore(env):
            first = self.first_version(env)
            return self.file(env)._add_version(
                source=RESTORED,
                user=env.ref("base.user_admin"),
                restored_from=first,
            )

        attempts, _second = self.race(lambda env: save(self.file(env), "uploaded"), restore)

        self.assertEqual(attempts, 2)
        self.assertEqual(self.versions(), ([(1, SYNCED), (2, SYNCED), (3, RESTORED)], 3))

    def test_two_first_saves_of_one_new_path_make_one_file(self):
        def first_save(env):
            folder = env[MODEL_LABORATORY_FOLDER].browse(self.folder_id)
            return save(env[MODEL_LABORATORY_FILE]._get_or_create(folder, "HPLC/new.csv"), "first")

        def second_save(env):
            folder = env[MODEL_LABORATORY_FOLDER].browse(self.folder_id)
            return save(env[MODEL_LABORATORY_FILE]._get_or_create(folder, "hplc/NEW.csv"), "second")

        attempts, version_id = self.race(first_save, second_save)

        def work(env):
            files = env[MODEL_LABORATORY_FILE].search([("folder_id", "=", self.folder_id), ("path", "ilike", "new")])
            return files.path, files.version_ids.sorted("number").mapped("number"), files.current_version_id.id

        self.assertEqual(attempts, 2)
        self.assertEqual(self.committed(work), ("HPLC/new.csv", [1, 2], version_id))
