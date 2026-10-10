from odoo.tests import tagged
from odoo.tools import mute_logger

from .jobs_case import JOB_LOGGER, JobsCase


@tagged("post_install", "-at_install")
class TestJobClaimTimeout(JobsCase):
    def test_an_item_claimed_longer_than_the_timeout_counts_an_attempt_and_goes_back_to_pending(self):
        handled = self.record_handler()
        stale = self.queue("stale")
        stale.write({"status": "running", "claimed_at": self.minutes_ago(self.job.claim_timeout_minutes + 1)})
        fresh = self.queue("fresh")
        fresh.write({"status": "running", "claimed_at": self.minutes_ago(1)})

        self.run_pass()

        self.assertEqual((stale.status, stale.attempts), ("pending", 1))
        self.assertIn("claim timeout", stale.last_error)
        self.assertGreater(stale.next_attempt_at, stale.claimed_at or stale.create_date)
        self.assertEqual((fresh.status, fresh.attempts), ("running", 0))
        self.assertEqual(handled, [])
        self.assertIn("abandoned claim released", self.job.run_ids.log)

    def test_a_released_item_is_done_by_a_later_pass(self):
        handled = self.record_handler()
        stale = self.queue("stale")
        stale.write({"status": "running", "claimed_at": self.minutes_ago(self.job.claim_timeout_minutes + 1)})

        self.run_pass()
        stale.next_attempt_at = self.minutes_ago(0)
        self.run_pass()

        self.assertEqual((stale.status, handled), ("done", ["stale"]))

    def test_an_abandoned_item_at_its_last_attempt_is_failed_and_notified(self):
        self.record_handler()
        self.job.max_attempts = 1
        stale = self.queue("stale")
        stale.write({"status": "running", "claimed_at": self.minutes_ago(self.job.claim_timeout_minutes + 1)})

        with mute_logger(JOB_LOGGER):
            self.run_pass()

        self.assertEqual((stale.status, stale.attempts), ("failed", 1))
