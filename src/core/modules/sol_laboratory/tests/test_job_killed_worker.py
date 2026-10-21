import time
from datetime import timedelta
from unittest.mock import patch

import psycopg2

from odoo import fields, sql_db
from odoo.tests import tagged
from odoo.tools import mute_logger

from .laboratory_files_concurrency_case import QUIET, LaboratoryFilesConcurrencyCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_CRON_PROGRESS,
    MODEL_JOB_ITEM,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_laboratory.models.system.scheduled_job import CRON_PASS_KEY, CRON_PROGRESS_KEY

JOB_KEY = "test.killed"
HANDLER = "_handle_test_killed"
ITEM_KEY = "content:large-file"


@tagged("post_install", "-at_install")
class TestJobKilledWorker(LaboratoryFilesConcurrencyCase):
    """A cron batch on a real connection whose worker dies in a handler, as a killed worker or a lost connection leaves
    it: Postgres rolls back whatever the batch had not committed. What the tests commit is theirs to remove."""

    def setUp(self):
        super().setUp()
        self.job_id, self.cron_id = self.committed(self.prepare)
        self.addCleanup(self.committed, self.remove)

    def prepare(self, env):
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_audit_entry")
        self.last_entry_id = env.cr.fetchone()[0]
        jobs = env[MODEL_SCHEDULED_JOB].with_context(**QUIET, mail_create_nosubscribe=True)
        job = jobs.create({"key": JOB_KEY, "name": "Killed", "retry_delay_minutes": 5})
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

    def item(self):
        def work(env):
            item = env[MODEL_JOB_ITEM].search([("job_id", "=", self.job_id)])
            return item.status, item.attempts, item.claimed_at

        return self.committed(work)

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
