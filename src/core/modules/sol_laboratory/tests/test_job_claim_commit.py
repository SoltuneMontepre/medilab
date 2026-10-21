import time
from datetime import timedelta
from unittest.mock import patch

import psycopg2

from odoo import fields, sql_db
from odoo.tests import tagged
from odoo.tools import mute_logger

from .jobs_case import JOB_LOGGER
from .laboratory_files_concurrency_case import QUIET, LaboratoryFilesConcurrencyCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_CRON_PROGRESS,
    MODEL_JOB_ITEM,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_laboratory.models.system.scheduled_job import (
    CRON_PASS_KEY,
    CRON_PROGRESS_KEY,
    PermanentJobError,
)

JOB_KEY = "test.claim_commit"
HANDLER = "_handle_test_claim_commit"
ITEM_KEY = "content:large-file"
# The item a failing handler queues before it raises; the rollback must remove it.
WRITTEN_KEY = "written-by-the-handler"


@tagged("post_install", "-at_install")
class TestJobClaimCommit(LaboratoryFilesConcurrencyCase):
    """A cron batch on a real connection commits its claims before its handler runs. A worker that dies in the handler,
    as a killed worker or a lost connection leaves it, rolls back only what the handler did; a handler that raises is
    handled by the retry rules as before. What the tests commit is theirs to remove."""

    def setUp(self):
        super().setUp()
        self.job_id, self.cron_id = self.committed(self.prepare)
        self.addCleanup(self.committed, self.remove)

    def prepare(self, env):
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_audit_entry")
        self.last_entry_id = env.cr.fetchone()[0]
        jobs = env[MODEL_SCHEDULED_JOB].with_context(**QUIET, mail_create_nosubscribe=True)
        job = jobs.create({"key": JOB_KEY, "name": "Claim commit", "retry_delay_minutes": 5})
        job.queue(JOB_KEY, ITEM_KEY)
        return job.id, job.cron_id.id

    def remove(self, env):
        # Jobs refuse deletion while their cron refers to them, so the data these tests committed is removed with SQL.
        cr = env.cr
        cr.execute(
            "DELETE FROM medilab_audit_change WHERE entry_id IN (SELECT id FROM medilab_audit_entry WHERE id > %s)",
            [self.last_entry_id],
        )
        cr.execute("DELETE FROM medilab_audit_entry WHERE id > %s", [self.last_entry_id])
        cr.execute("DELETE FROM medilab_job_item WHERE job_id = %s", [self.job_id])
        cr.execute("DELETE FROM medilab_job_run WHERE job_id = %s", [self.job_id])
        cr.execute(
            "DELETE FROM mail_followers WHERE res_model = %s AND res_id = %s", [MODEL_SCHEDULED_JOB, self.job_id]
        )
        cr.execute("DELETE FROM mail_message WHERE model = %s AND res_id = %s", [MODEL_SCHEDULED_JOB, self.job_id])
        cr.execute("DELETE FROM mail_activity WHERE res_model = %s AND res_id = %s", [MODEL_SCHEDULED_JOB, self.job_id])
        cr.execute("DELETE FROM medilab_scheduled_job WHERE id = %s", [self.job_id])
        cr.execute("SELECT ir_actions_server_id FROM ir_cron WHERE id = %s", [self.cron_id])
        (action_id,) = cr.fetchone()
        cr.execute("DELETE FROM ir_cron WHERE id = %s", [self.cron_id])
        cr.execute("DELETE FROM ir_act_server WHERE id = %s", [action_id])

    def handle_with(self, handler):
        patcher = patch.object(type(self.env[MODEL_SCHEDULED_JOB]), HANDLER, handler, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_batch(self, env):
        """One batch of the job with the context Odoo's cron gives it: its progress record, its cron and the end of its
        pass."""
        progress = env[MODEL_IR_CRON_PROGRESS].create({"cron_id": self.cron_id})
        job = env[MODEL_SCHEDULED_JOB].browse(self.job_id)
        context = {CRON_PROGRESS_KEY: progress.id, "cron_id": self.cron_id, CRON_PASS_KEY: time.monotonic() + 120}
        job.with_context(**context)._run_batch()

    def run_killed_batch(self):
        """A batch whose handler ends the worker's connection, as a killed worker does."""

        def die(job, item):
            job.env.cr.execute("SELECT pg_terminate_backend(pg_backend_pid())")

        self.handle_with(die)
        cursor = sql_db.db_connect(self.registry.db_name).cursor()
        try:
            with mute_logger("odoo.sql_db"), self.assertRaises(psycopg2.Error):
                self.run_batch(self.environment(cursor))
        finally:
            # The batch died in an item's savepoint, which its connection can no longer release.
            cursor.transaction = None
            cursor.close()

    def run_failing_batch(self, error):
        """A batch whose handler writes, then raises the error: it queues another item and changes the payload of its
        own."""

        def fail(job, item):
            job.queue(JOB_KEY, WRITTEN_KEY)
            item.payload = {"written": True}
            raise error

        self.handle_with(fail)
        with mute_logger(JOB_LOGGER):
            self.committed(self.run_batch)

    def item(self):
        def work(env):
            item = env[MODEL_JOB_ITEM].search([("job_id", "=", self.job_id), ("item_key", "=", ITEM_KEY)])
            return item.status, item.attempts, item.claimed_at

        return self.committed(work)

    def failure(self):
        """What the failed attempt left: the item's error, next attempt and payload, the item keys of the job, and the
        log of its run."""

        def work(env):
            items = env[MODEL_JOB_ITEM].search([("job_id", "=", self.job_id)])
            item = items.filtered(lambda item: item.item_key == ITEM_KEY)
            run = env[MODEL_SCHEDULED_JOB].browse(self.job_id).run_ids
            return item.last_error, item.next_attempt_at, item.payload, items.mapped("item_key"), run.log

        return self.committed(work)

    def assertHandlerWritesRolledBack(self):
        _error, _next_attempt_at, payload, item_keys, _log = self.failure()
        self.assertFalse(payload)
        self.assertEqual(item_keys, [ITEM_KEY])

    def test_a_handler_that_raises_counts_an_attempt_and_its_writes_are_rolled_back(self):
        self.run_failing_batch(ValueError("the bucket is unreachable"))

        status, attempts, _claimed_at = self.item()
        error, next_attempt_at, _payload, _item_keys, log = self.failure()
        self.assertEqual((status, attempts), ("pending", 1))
        self.assertIn("the bucket is unreachable", error)
        self.assertIn("the bucket is unreachable", log)
        retry_delay = self.committed(lambda env: env[MODEL_SCHEDULED_JOB].browse(self.job_id).retry_delay_minutes)
        self.assertAlmostEqual(
            next_attempt_at, fields.Datetime.now() + timedelta(minutes=retry_delay), delta=timedelta(minutes=1)
        )
        self.assertHandlerWritesRolledBack()

    def test_a_handler_that_raises_at_its_last_attempt_fails_the_item_and_notifies(self):
        self.committed(lambda env: env[MODEL_SCHEDULED_JOB].browse(self.job_id).write({"max_attempts": 1}))
        notified = []
        self.patch(type(self.env[MODEL_SCHEDULED_JOB]), "_notify_failed_item", lambda job, item: notified.append(1))

        self.run_failing_batch(ValueError("the bucket is unreachable"))

        self.assertEqual(self.item()[:2], ("failed", 1))
        self.assertEqual(notified, [1])
        self.assertHandlerWritesRolledBack()

    def test_a_permanent_error_fails_the_item_at_once_and_its_writes_are_rolled_back(self):
        self.run_failing_batch(PermanentJobError("the object is not the content"))

        self.assertEqual(self.item()[:2], ("failed", 1))
        self.assertEqual(self.failure()[0], "the object is not the content")
        self.assertHandlerWritesRolledBack()

    def set_item(self, vals):
        self.committed(lambda env: env[MODEL_JOB_ITEM].search([("job_id", "=", self.job_id)]).write(vals))

    def test_a_worker_killed_in_a_handler_leaves_its_item_claimed(self):
        self.run_killed_batch()

        status, attempts, claimed_at = self.item()
        self.assertEqual((status, attempts), ("running", 0))
        self.assertTrue(claimed_at)

    def test_the_item_of_a_killed_worker_is_taken_again_only_after_the_claim_timeout(self):
        self.run_killed_batch()
        handled = []
        self.handle_with(lambda job, item: handled.append(item.item_key))

        self.committed(self.run_batch)
        self.assertEqual((self.item()[0], handled), ("running", []))

        claim_timeout = self.committed(lambda env: env[MODEL_SCHEDULED_JOB].browse(self.job_id).claim_timeout_minutes)
        self.set_item({"claimed_at": fields.Datetime.now() - timedelta(minutes=claim_timeout + 1)})
        self.committed(self.run_batch)
        self.assertEqual(self.item()[:2], ("pending", 1))

        self.set_item({"next_attempt_at": fields.Datetime.now()})
        self.committed(self.run_batch)
        self.assertEqual((self.item()[:2], handled), (("done", 1), [ITEM_KEY]))
