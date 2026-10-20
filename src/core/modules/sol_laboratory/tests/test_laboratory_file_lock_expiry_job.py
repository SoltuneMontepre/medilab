from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .laboratory_file_locks_case import LaboratoryFileLocksCase
from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB

EXPIRE = "laboratory_file_locks.expire"
CLEANUP = "cleanup"


@tagged("post_install", "-at_install")
class TestLaboratoryFileLockExpiryJob(LaboratoryFileLocksCase):
    def test_the_job_expires_locks_that_were_not_renewed_and_leaves_the_others(self):
        abandoned = self.lock_as(self.tester)
        self.pass_expiry(abandoned)
        expired_at = abandoned.expires_at
        held = self.lock_as(self.member, self.file_in("working"))

        self.env[MODEL_SCHEDULED_JOB]._run_key(EXPIRE)

        self.assertRecordValues(abandoned, [{"status": "expired", "released_at": expired_at}])
        self.assertEqual(held.status, "active")

    def test_a_lock_renewed_after_it_was_queued_is_left_and_expires_when_it_expires_again(self):
        job = self.env[MODEL_SCHEDULED_JOB]._by_key(EXPIRE)
        lock = self.lock_as(self.tester)
        self.pass_expiry(lock)
        job._queue_laboratory_file_locks_expire()
        lock.sudo().expires_at = lock._new_expiry()
        job._run_batch()
        self.assertEqual(lock.status, "active")

        self.pass_expiry(lock, minutes=2)
        self.env[MODEL_SCHEDULED_JOB]._run_key(EXPIRE)

        self.assertEqual(lock.status, "expired")

    def test_the_cleanup_job_removes_ended_locks_after_the_retention_period_of_locks(self):
        old = self.lock_as(self.tester)
        self.file.with_user(self.tester)._unlock()
        old.sudo().released_at = fields.Datetime.now() - timedelta(days=91)
        recent = self.lock_as(self.tester)
        self.file.with_user(self.tester)._unlock()
        held = self.lock_as(self.member)
        job = self.env[MODEL_SCHEDULED_JOB]._by_key(CLEANUP)

        job._run_batch()
        job._run_batch()

        self.assertEqual((old | recent | held).exists(), recent | held)
