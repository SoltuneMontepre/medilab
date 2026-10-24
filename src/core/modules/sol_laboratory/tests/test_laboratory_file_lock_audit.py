from odoo.tests import tagged

from .audit_case import AuditLookup
from .laboratory_file_locks_case import LaboratoryFileLocksCase
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FILE, MODEL_LABORATORY_FILE_LOCK


@tagged("post_install", "-at_install")
class TestLaboratoryFileLockAudit(AuditLookup, LaboratoryFileLocksCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.auditor = cls.new_auditor()

    def lock_entries(self):
        history = self.history(self.file, self.auditor)
        return history.filtered(lambda entry: entry.document_model == MODEL_LABORATORY_FILE_LOCK).sorted("id")

    def test_locking_unlocking_expiry_and_release_are_in_the_file_history(self):
        unlocked = self.lock_as(self.tester)
        self.file.with_user(self.tester)._renew_lock()
        self.file.with_user(self.tester)._unlock()
        expired = self.lock_as(self.member)
        self.pass_expiry(expired)
        released = self.lock_as(self.tester)
        released.with_user(self.administrator).action_release()

        entries = self.lock_entries()
        self.assertEqual(
            [(entry.document_id, entry.action, self.changes(entry).get("status")) for entry in entries],
            [
                (unlocked.id, "create", (False, "active")),
                (unlocked.id, "edit", ("active", "released")),
                (expired.id, "create", (False, "active")),
                (expired.id, "edit", ("active", "expired")),
                (released.id, "create", (False, "active")),
                (released.id, "edit", ("active", "released")),
            ],
        )
        self.assertEqual(
            [entry.user_id for entry in entries],
            [self.tester, self.tester, self.member, self.tester, self.tester, self.administrator],
        )
        self.assertEqual(
            self.changes(entries[-1])["released_by_id"][1], f"{self.administrator.name} (#{self.administrator.id})"
        )
        self.assertEqual(
            {(entry.parent_model, entry.parent_id) for entry in entries}, {(MODEL_LABORATORY_FILE, self.file.id)}
        )

    def test_renewing_a_lock_writes_no_entry(self):
        self.lock_as(self.tester)
        before = len(self.lock_entries())

        self.file.with_user(self.tester)._renew_lock()
        self.lock_as(self.tester)

        self.assertEqual(len(self.lock_entries()), before)
