from datetime import timedelta
from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .jobs_case import JOB_KEY, JOB_LOGGER, JobsCase
from odoo.addons.sol_laboratory.constants.models import MODEL_IR_CRON_TRIGGER, MODEL_JOB_RUN


@tagged("post_install", "-at_install")
class TestJobRun(JobsCase):
    def test_last_run_summary_tracks_latest_runs_and_related_changes(self):
        older_start = self.minutes_ago(30)
        older_end = older_start + timedelta(seconds=20)
        older = self.env[MODEL_JOB_RUN].create(
            {"job_id": self.job.id, "started_at": older_start, "ended_at": older_end, "status": "succeeded"}
        )
        latest_start = self.minutes_ago(10)
        latest_end = latest_start + timedelta(seconds=40)
        latest = self.env[MODEL_JOB_RUN].create(
            {"job_id": self.job.id, "started_at": latest_start, "ended_at": latest_end, "status": "partly_failed"}
        )

        self.assertEqual(self.job.last_run_id, latest)
        self.assertEqual(self.job.last_run_status, "partly_failed")
        self.assertEqual(self.job.last_run_duration, 40)

        changed_end = latest_start + timedelta(seconds=65)
        latest.write({"status": "failed", "ended_at": changed_end})

        self.assertEqual(self.job.last_run_status, "failed")
        self.assertEqual(self.job.last_run_duration, 65)

        latest.write({"started_at": older_start - timedelta(minutes=1)})

        self.assertEqual(self.job.last_run_id, older)
        self.assertEqual(self.job.last_run_status, "succeeded")
        self.assertEqual(self.job.last_run_duration, 20)

    def test_two_passes_in_a_row_do_each_item_once(self):
        handled = self.record_handler()
        self.queue("a")
        self.queue("b")

        self.run_pass()
        self.run_pass()

        self.assertEqual(sorted(handled), ["a", "b"])
        self.assertEqual(self.items("done").mapped("item_key"), ["a", "b"])
        self.assertEqual(self.job.run_ids.mapped("status"), ["succeeded", "succeeded"])

    def test_the_batches_of_one_pass_share_one_run(self):
        handled = self.record_handler()
        self.job.batch_size = 2
        for index in range(5):
            self.queue(f"item:{index}")

        self.run_pass()

        self.assertEqual(len(handled), 5)
        self.assertEqual(len(self.job.run_ids), 1)
        run = self.job.run_ids
        self.assertEqual((run.status, run.done_count, run.failed_count), ("succeeded", 5, 0))
        self.assertEqual(run.log.count(": done"), 5)

    def test_the_items_the_finder_queues_are_done_in_the_same_run(self):
        handled = self.record_handler()
        with freeze_time("2026-10-20 08:00:00") as clock:

            def finder(job):
                # The clock reaches the next second after the run started.
                clock.tick()
                job.queue(JOB_KEY, "found")

            self.find_with(finder)
            self.job._run_batch()

        self.assertEqual(handled, ["found"])
        self.assertEqual(self.items("done").mapped("item_key"), ["found"])

    def test_a_handler_returning_a_time_defers_the_item_without_an_attempt(self):
        later = fields.Datetime.now() + timedelta(hours=1)
        self.handle_with(lambda job, item: later)
        item = self.queue("poll:1")

        self.run_pass()

        self.assertEqual((item.status, item.attempts, item.next_attempt_at), ("pending", 0, later))
        self.assertIn("deferred", self.job.run_ids.log)

    def test_a_pass_without_due_items_succeeds(self):
        self.record_handler()

        self.run_pass()

        self.assertEqual(self.job.run_ids.mapped("status"), ["succeeded"])

    def test_a_missing_handler_fails_the_run_and_leaves_the_items(self):
        item = self.queue("a")

        with mute_logger(JOB_LOGGER):
            self.run_pass()

        self.assertEqual(self.job.run_ids.status, "failed")
        self.assertIn("_handle_test_echo", self.job.run_ids.log)
        self.assertEqual(item.status, "pending")

    def test_run_now_triggers_the_cron_and_the_next_pass_records_who_asked(self):
        self.record_handler()
        self.queue("a")

        self.job.action_run()

        trigger = self.env[MODEL_IR_CRON_TRIGGER].search([("cron_id", "=", self.job.cron_id.id)])
        self.assertTrue(trigger)
        self.assertLessEqual(trigger.call_at, fields.Datetime.now())
        self.assertEqual(self.job.run_requested_by_id, self.env.user)

        self.run_pass()

        self.assertEqual(self.job.run_ids.triggered_by_id, self.env.user)
        self.assertFalse(self.job.run_requested_by_id)

    def test_run_now_needs_an_active_schedule(self):
        self.job.cron_active = False

        with self.assertRaises(UserError):
            self.job.action_run()
