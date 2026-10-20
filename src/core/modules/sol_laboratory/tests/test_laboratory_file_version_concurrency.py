import hashlib
import threading
import time
import uuid

from odoo import api, sql_db
from odoo.api import SUPERUSER_ID
from odoo.http.retrying import retrying
from odoo.orm.environments import Transaction
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.sol_laboratory.constants.laboratory_files import CONFLICT, EDITED_ONLINE, RESTORED, SYNCED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_LABORATORY_FOLDER,
)

# How long the first save keeps its transaction open once the second one is saving, so the second waits on the file.
HOLD_SECONDS = 0.5


def save(file, content, source=SYNCED, **values):
    sha256 = hashlib.sha256(content.encode()).hexdigest()
    return file._add_version(
        sha256=sha256,
        size=len(content),
        storage_key=f"test/{sha256}",
        source=source,
        user=file.env.ref("base.user_admin"),
        **values,
    )


@tagged("post_install", "-at_install")
class TestLaboratoryFileVersionConcurrency(TransactionCase):
    """Two real database transactions saving the same file at once, the second one through Odoo's request retrying."""

    def setUp(self):
        super().setUp()
        self.folder_id, self.file_id, self.first_id = self.committed(self.prepare)
        self.addCleanup(self.committed, self.remove)

    def committed(self, work):
        with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
            return work(self.environment(cursor))

    def environment(self, cursor):
        # An environment looks its registry up by name, which waits on the lock the test run holds, so the thread of
        # these tests would never get one; they use the registry already loaded.
        cursor.transaction = Transaction(self.registry)
        cursor.transaction._check_signaling(cursor)
        return api.Environment(cursor, SUPERUSER_ID, {})

    def prepare(self, env):
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_audit_entry")
        self.last_entry_id = env.cr.fetchone()[0]
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
        cr.execute("DELETE FROM medilab_laboratory_file WHERE folder_id = %s", [self.folder_id])
        cr.execute("DELETE FROM medilab_laboratory_folder_member WHERE folder_id = %s", [self.folder_id])
        cr.execute("DELETE FROM medilab_laboratory_folder WHERE id = %s", [self.folder_id])

    def race(self, first_save, second_save):
        """The first save stores its version and keeps its transaction open until the second one is saving, then
        commits. The second save runs as a request does, through Odoo's retrying. The number of times the second one
        ran and the id of what it returned."""
        stored = threading.Event()
        second_saving = threading.Event()
        errors = []

        def first():
            try:
                with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
                    env = self.environment(cursor)
                    first_save(env)
                    env.flush_all()
                    # Committing resets the transaction, which also looks the registry up by name; the save is flushed,
                    # so the cursor commits it without one.
                    cursor.transaction = None
                    stored.set()
                    if not second_saving.wait(timeout=10):
                        errors.append(TimeoutError("the second save never started"))
                        return
                    time.sleep(HOLD_SECONDS)
            except Exception as error:
                errors.append(error)
            finally:
                stored.set()

        attempts = []
        thread = threading.Thread(target=first)
        thread.start()
        try:
            with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
                env = self.environment(cursor)

                def run():
                    attempts.append(len(attempts) + 1)
                    if len(attempts) == 1:
                        self.assertTrue(stored.wait(timeout=10), "the first save never stored its version")
                        second_saving.set()
                    return second_save(env).id

                with mute_logger("odoo.sql_db", "odoo.http.retrying"):
                    result = retrying(run, env)
        finally:
            thread.join(15)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors, errors)
        return len(attempts), result

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
                sha256=first.sha256,
                size=first.size,
                storage_key=first.storage_key,
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
