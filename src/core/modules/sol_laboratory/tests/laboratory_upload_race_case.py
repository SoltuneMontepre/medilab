import uuid

from odoo.tests import new_test_user

from .laboratory_files_case import stored_content
from .laboratory_files_concurrency_case import LaboratoryFilesConcurrencyCase
from odoo.addons.sol_laboratory.constants.laboratory_files import SYNCED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_CONTENT,
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FOLDER,
    MODEL_RES_USERS,
)
from odoo.addons.sol_laboratory.constants.xml_ids import LABORATORY_FILES_GROUP
from odoo.addons.sol_laboratory.services import laboratory_bucket


class LaboratoryUploadRaceCase(LaboratoryFilesConcurrencyCase):
    """A tester with a computer and a folder holding one file, committed for tests of uploads in real database
    transactions. What the tests commit, and write to the bucket, is theirs to remove."""

    def setUp(self):
        super().setUp()
        self.committed(self.prepare_records)
        self.addCleanup(self.committed, self.remove)

    def prepare_records(self, env):
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_audit_entry")
        self.last_entry_id = env.cr.fetchone()[0]
        self.last_content_id = self.last_content(env)
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_job_item")
        self.last_item_id = env.cr.fetchone()[0]
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_job_run")
        self.last_run_id = env.cr.fetchone()[0]
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM ir_cron_progress")
        self.last_progress_id = env.cr.fetchone()[0]
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM ir_cron_trigger")
        self.last_trigger_id = env.cr.fetchone()[0]
        suffix = uuid.uuid4().hex[:8]
        tester = new_test_user(env, login=f"upload.{suffix}", groups=f"base.group_user,{LABORATORY_FILES_GROUP}")
        self.tester_id = tester.id
        folder = env[MODEL_LABORATORY_FOLDER].create({"name": f"Uploads {suffix}", "owner_id": tester.id})
        self.folder_id = folder.id
        devices = env[MODEL_LABORATORY_DEVICE].with_user(tester)
        _key, key_id = devices._new_key("PC-HPLC-01")
        device = devices.sudo().create(
            {
                "user_id": tester.id,
                "client_uid": suffix,
                "name": "PC-HPLC-01",
                "platform": "windows",
                "api_key_id": key_id,
            }
        )
        self.device_id = device.id
        file = env[MODEL_LABORATORY_FILE]._get_or_create(folder, "HPLC/run-01.csv")
        self.file_id = file.id
        self.first_id = file._add_version(content=stored_content(env, "run 1"), source=SYNCED, user=tester).id

    def remove(self, env):
        # Uploads, files, versions, changes and content refuse deletion, so what these tests committed is removed with
        # SQL; so are the person, the computer and their key.
        cr = env.cr
        contents = env[MODEL_LABORATORY_CONTENT].search([("id", ">", self.last_content_id)])
        for content in contents.filtered("object_key"):
            laboratory_bucket.delete(content.object_key)
        cr.execute(
            "DELETE FROM medilab_audit_change WHERE entry_id IN (SELECT id FROM medilab_audit_entry WHERE id > %s)",
            [self.last_entry_id],
        )
        cr.execute("DELETE FROM medilab_audit_entry WHERE id > %s", [self.last_entry_id])
        cr.execute("DELETE FROM medilab_job_item WHERE id > %s", [self.last_item_id])
        cr.execute("DELETE FROM medilab_job_run WHERE id > %s", [self.last_run_id])
        cr.execute("DELETE FROM ir_cron_progress WHERE id > %s", [self.last_progress_id])
        cr.execute("DELETE FROM ir_cron_trigger WHERE id > %s", [self.last_trigger_id])
        cr.execute("DELETE FROM medilab_laboratory_upload WHERE folder_id = %s", [self.folder_id])
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
        cr.execute("SELECT api_key_id FROM medilab_laboratory_device WHERE id = %s", [self.device_id])
        (key_id,) = cr.fetchone()
        cr.execute("DELETE FROM medilab_laboratory_device WHERE id = %s", [self.device_id])
        cr.execute("DELETE FROM res_users_apikeys WHERE id = %s", [key_id])
        user = env[MODEL_RES_USERS].browse(self.tester_id)
        partner = user.partner_id
        user.unlink()
        partner.unlink()

    def tester(self, env):
        return env[MODEL_RES_USERS].browse(self.tester_id)
