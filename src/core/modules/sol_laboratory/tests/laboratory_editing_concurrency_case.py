import uuid
from datetime import timedelta

from odoo import fields

from .editing_service import use_editing_service
from .laboratory_files_case import stored_content
from .laboratory_files_concurrency_case import LaboratoryFilesConcurrencyCase
from odoo.addons.sol_laboratory.constants.laboratory_files import SYNCED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_EDITING_SESSION,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FOLDER,
)
from odoo.addons.sol_laboratory.constants.settings import DEFAULT_LABORATORY_EDITING_IDLE_HOURS


class LaboratoryEditingConcurrencyCase(LaboratoryFilesConcurrencyCase):
    """Committed editing fixtures shared by model races and the independent HTTP server tests."""

    def setUp(self):
        super().setUp()
        self.folder_id, self.file_id = self.committed(self.prepare)
        self.addCleanup(self.committed, self.remove)
        use_editing_service(self)

    def prepare(self, env):
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_audit_entry")
        self.last_entry_id = env.cr.fetchone()[0]
        self.last_content_id = self.last_content(env)
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
        self.remove_contents(cr, self.last_content_id)
        cr.execute("DELETE FROM medilab_laboratory_file WHERE folder_id = %s", [self.folder_id])
        cr.execute("DELETE FROM medilab_laboratory_folder_member WHERE folder_id = %s", [self.folder_id])
        cr.execute("DELETE FROM medilab_laboratory_folder WHERE id = %s", [self.folder_id])

    def upload(self, file, content):
        return file._add_version(
            content=stored_content(file.env, content), source=SYNCED, user=file.env.ref("base.user_admin")
        )

    def file(self, env):
        return env[MODEL_LABORATORY_FILE].browse(self.file_id).with_user(env.ref("base.user_admin"))

    def open(self, env):
        return env[MODEL_LABORATORY_EDITING_SESSION].with_user(env.ref("base.user_admin"))._open_for(self.file(env))

    def session(self, env):
        return env[MODEL_LABORATORY_EDITING_SESSION].search([("file_id", "=", self.file_id)], order="id desc", limit=1)

    def store(self, env, content):
        admin = env.ref("base.user_admin")
        return self.session(env)._store_save(content=stored_content(env, content), editor=admin, editors=admin)

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
