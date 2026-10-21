import hashlib
import uuid
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .laboratory_files_concurrency_case import LaboratoryFilesConcurrencyCase
from odoo.addons.sol_laboratory.constants.laboratory_editing import COMMITTED, OPEN, SESSION_CONFLICT
from odoo.addons.sol_laboratory.constants.laboratory_files import CONFLICT, EDITED_ONLINE, SYNCED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_EDITING_SESSION,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FOLDER,
)
from odoo.addons.sol_laboratory.constants.settings import DEFAULT_LABORATORY_EDITING_IDLE_HOURS


def sha(content):
    return hashlib.sha256(content.encode()).hexdigest()


@tagged("post_install", "-at_install")
class TestLaboratoryEditingConcurrency(LaboratoryFilesConcurrencyCase):
    """Two real database transactions opening, saving and expiring an editing session at once, the second one through
    Odoo's request retrying."""

    def setUp(self):
        super().setUp()
        self.folder_id, self.file_id = self.committed(self.prepare)
        self.addCleanup(self.committed, self.remove)

    def prepare(self, env):
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_audit_entry")
        self.last_entry_id = env.cr.fetchone()[0]
        folder = env[MODEL_LABORATORY_FOLDER].create(
            {"name": f"Concurrency {uuid.uuid4().hex[:8]}", "owner_id": env.ref("base.user_admin").id}
        )
        file = env[MODEL_LABORATORY_FILE]._get_or_create(folder, "Kết quả HPLC.xlsx")
        self.upload(file, "bản 1")
        return folder.id, file.id

    def remove(self, env):
        # Sessions, files, versions and changes refuse deletion, so the data these tests committed is removed with SQL.
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
        cr.execute(
            "DELETE FROM medilab_laboratory_editing_session WHERE file_id IN "
            "(SELECT id FROM medilab_laboratory_file WHERE folder_id = %s)",
            [self.folder_id],
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

    def upload(self, file, content):
        return file._add_version(
            sha256=sha(content),
            size=len(content),
            storage_key=f"test/{sha(content)}",
            source=SYNCED,
            user=file.env.ref("base.user_admin"),
        )

    def file(self, env):
        return env[MODEL_LABORATORY_FILE].browse(self.file_id).with_user(env.ref("base.user_admin"))

    def open(self, env):
        return env[MODEL_LABORATORY_EDITING_SESSION].with_user(env.ref("base.user_admin"))._open_for(self.file(env))

    def session(self, env):
        return env[MODEL_LABORATORY_EDITING_SESSION].search([("file_id", "=", self.file_id)], order="id desc", limit=1)

    def store(self, env, content):
        admin = env.ref("base.user_admin")
        return self.session(env)._store_save(
            sha256=sha(content), size=len(content), storage_key=f"test/{sha(content)}", editor=admin, editors=admin
        )

    def expire(self, env):
        session = self.session(env)
        session._expire()
        return session

    def go_idle(self, env):
        session = self.open(env)
        session.sudo().last_activity_at = fields.Datetime.now() - timedelta(
            hours=DEFAULT_LABORATORY_EDITING_IDLE_HOURS + 1
        )

    def state(self):
        def work(env):
            file = env[MODEL_LABORATORY_FILE].browse(self.file_id)
            sessions = env[MODEL_LABORATORY_EDITING_SESSION].search([("file_id", "=", self.file_id)], order="id")
            return (
                [(version.number, version.source) for version in file.version_ids.sorted("number")],
                [(session.status, session.committed_version_id.number) for session in sessions],
            )

        return self.committed(work)

    def test_two_people_opening_a_file_at_once_make_one_session(self):
        first_id = []
        attempts, second_id = self.race(lambda env: first_id.append(self.open(env).id), self.open)

        self.assertEqual(attempts, 2)
        self.assertEqual(second_id, first_id[0])
        self.assertEqual(self.state()[1], [(OPEN, False)])

    def test_two_calls_of_one_save_at_once_store_one_version(self):
        self.committed(self.open)

        attempts, version_id = self.race(
            lambda env: self.store(env, "bản sửa trực tuyến"), lambda env: self.store(env, "bản sửa trực tuyến")
        )

        self.assertEqual(attempts, 2)
        self.assertEqual(self.state(), ([(1, SYNCED), (2, EDITED_ONLINE)], [(COMMITTED, 2)]))
        self.assertEqual(self.committed(lambda env: self.session(env).committed_version_id.id), version_id)

    def test_an_upload_and_an_online_save_at_once_get_the_next_two_numbers_and_the_save_is_a_conflict(self):
        self.committed(self.open)

        attempts, _version_id = self.race(
            lambda env: self.upload(self.file(env), "bản 2 từ máy tính"),
            lambda env: self.store(env, "bản sửa trực tuyến"),
        )

        self.assertEqual(attempts, 2)
        self.assertEqual(self.state(), ([(1, SYNCED), (2, SYNCED), (3, CONFLICT)], [(SESSION_CONFLICT, 3)]))

    def test_a_save_arriving_while_its_session_expires_is_stored(self):
        self.committed(self.go_idle)

        attempts, _version_id = self.race(self.expire, lambda env: self.store(env, "bản sửa 13 giờ"))

        self.assertEqual(attempts, 2)
        self.assertEqual(self.state(), ([(1, SYNCED), (2, EDITED_ONLINE)], [(COMMITTED, 2)]))

    def test_expiring_a_session_its_save_just_ended_changes_nothing(self):
        self.committed(self.go_idle)

        attempts, _session_id = self.race(lambda env: self.store(env, "bản sửa 13 giờ"), self.expire)

        self.assertEqual(attempts, 2)
        self.assertEqual(self.state(), ([(1, SYNCED), (2, EDITED_ONLINE)], [(COMMITTED, 2)]))
