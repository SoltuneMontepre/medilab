import uuid

from odoo.fields import Command
from odoo.tests import new_test_user, tagged

from .laboratory_files_case import stored_content
from .laboratory_files_concurrency_case import LaboratoryFilesConcurrencyCase
from odoo.addons.sol_laboratory.constants.laboratory_files import LOCKED, MEMBER_ROLE, SYNCED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_LOCK,
    MODEL_LABORATORY_FOLDER,
    MODEL_RES_USERS,
)
from odoo.addons.sol_laboratory.constants.xml_ids import LABORATORY_FILES_GROUP
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError


def save(file, content, user):
    return file._add_version(content=stored_content(file.env, content), source=SYNCED, user=user)


@tagged("post_install", "-at_install")
class TestLaboratoryFileLockConcurrency(LaboratoryFilesConcurrencyCase):
    """Two people locking and saving the same file at once, in real database transactions."""

    def setUp(self):
        super().setUp()
        self.committed(self.prepare)
        self.addCleanup(self.committed, self.remove)

    def prepare(self, env):
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_audit_entry")
        self.last_entry_id = env.cr.fetchone()[0]
        self.last_content_id = self.last_content(env)
        suffix = uuid.uuid4().hex[:8]
        groups = f"base.group_user,{LABORATORY_FILES_GROUP}"
        first, second = (new_test_user(env, login=f"lock.{name}.{suffix}", groups=groups) for name in ("one", "two"))
        self.first_id, self.second_id = first.id, second.id
        folder = env[MODEL_LABORATORY_FOLDER].create(
            {
                "name": f"Locks {suffix}",
                "owner_id": first.id,
                "member_ids": [Command.create({"user_id": second.id, "role": MEMBER_ROLE})],
            }
        )
        self.folder_id = folder.id
        file = env[MODEL_LABORATORY_FILE]._get_or_create(folder, "calibration.csv")
        self.file_id = file.id
        save(file, "calibration 1", first)

    def remove(self, env):
        # Locks, files, versions and changes are removed with SQL, as files refuse deletion; so are the audit entries
        # of what these tests committed, the people's contacts among them.
        cr = env.cr
        cr.execute("DELETE FROM medilab_audit_change WHERE entry_id > %s", [self.last_entry_id])
        cr.execute("DELETE FROM medilab_audit_entry WHERE id > %s", [self.last_entry_id])
        cr.execute("DELETE FROM medilab_laboratory_file_lock WHERE file_id = %s", [self.file_id])
        cr.execute("DELETE FROM medilab_laboratory_file_change WHERE folder_id = %s", [self.folder_id])
        cr.execute("UPDATE medilab_laboratory_file SET current_version_id = NULL WHERE id = %s", [self.file_id])
        cr.execute("DELETE FROM medilab_laboratory_file_version WHERE file_id = %s", [self.file_id])
        self.remove_contents(cr, self.last_content_id)
        cr.execute("DELETE FROM medilab_laboratory_file WHERE id = %s", [self.file_id])
        cr.execute("DELETE FROM medilab_laboratory_folder_member WHERE folder_id = %s", [self.folder_id])
        cr.execute("DELETE FROM medilab_laboratory_folder WHERE id = %s", [self.folder_id])
        users = env[MODEL_RES_USERS].browse([self.first_id, self.second_id])
        partners = users.partner_id
        users.unlink()
        partners.unlink()

    def file_as(self, env, user_id):
        return env[MODEL_LABORATORY_FILE].browse(self.file_id).with_user(user_id)

    def lock_as(self, user_id):
        return lambda env: self.file_as(env, user_id)._lock()

    def save_as(self, user_id, content):
        return lambda env: save(self.file_as(env, user_id), content, env[MODEL_RES_USERS].browse(user_id))

    def outcome(self):
        def work(env):
            file = env[MODEL_LABORATORY_FILE].browse(self.file_id)
            locks = env[MODEL_LABORATORY_FILE_LOCK].search([("file_id", "=", self.file_id), ("status", "=", "active")])
            return file.version_ids.sorted("number").mapped("number"), [(lock.id, lock.user_id.id) for lock in locks]

        return self.committed(work)

    def assertLocked(self, refusal):
        self.assertIsInstance(refusal, LaboratoryFileError)
        self.assertEqual(refusal.code, LOCKED)

    def test_two_people_locking_a_file_at_once_end_with_one_holder(self):
        attempts, refusal = self.race(self.lock_as(self.first_id), self.lock_as(self.second_id))

        self.assertEqual(attempts, 2)
        self.assertLocked(refusal)
        _versions, locks = self.outcome()
        self.assertEqual([user_id for _lock_id, user_id in locks], [self.first_id])

    def test_a_save_by_someone_else_while_the_file_is_being_locked_is_refused(self):
        attempts, refusal = self.race(self.lock_as(self.first_id), self.save_as(self.second_id, "calibration 2"))

        self.assertEqual(attempts, 2)
        self.assertLocked(refusal)
        self.assertEqual(self.outcome()[0], [1])

    def test_a_lock_taken_while_someone_else_saves_locks_the_saved_version(self):
        attempts, lock_id = self.race(self.save_as(self.second_id, "calibration 2"), self.lock_as(self.first_id))

        self.assertEqual(attempts, 2)
        self.assertEqual(self.outcome(), ([1, 2], [(lock_id, self.first_id)]))
