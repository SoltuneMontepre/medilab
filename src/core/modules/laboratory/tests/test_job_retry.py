from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged
from odoo.tools import mute_logger

from .jobs_case import JOB_LOGGER, JobsCase
from odoo.addons.laboratory.constants.models import MODEL_SCHEDULED_JOB
from odoo.addons.laboratory.models.system.scheduled_job import PermanentJobError


def fail(job, item):
    raise ValueError("the provider is down")


@tagged("post_install", "-at_install")
class TestJobRetry(JobsCase):
    def test_a_failure_is_logged_and_retried_with_a_doubling_delay(self):
        self.handle_with(fail)
        item = self.queue("a")

        for attempt, delay in ((1, 5), (2, 10), (3, 20)):
            item.next_attempt_at = fields.Datetime.now()
            with mute_logger(JOB_LOGGER):
                self.run_pass()
            with self.subTest(attempt=attempt):
                self.assertEqual((item.status, item.attempts), ("pending", attempt))
                self.assertIn("the provider is down", item.last_error)
                self.assertAlmostEqual(
                    item.next_attempt_at, fields.Datetime.now() + timedelta(minutes=delay), delta=timedelta(minutes=1)
                )
        self.assertIn("the provider is down", self.job.run_ids[0].log)
        self.assertEqual(set(self.job.run_ids.mapped("status")), {"failed"})

    def test_the_last_attempt_fails_the_item_and_notifies(self):
        self.handle_with(fail)
        self.job.max_attempts = 2
        item = self.queue("a")
        item.attempts = 1

        with (
            patch.object(type(self.env[MODEL_SCHEDULED_JOB]), "_notify_failed_item", autospec=True) as notify,
            mute_logger(JOB_LOGGER),
        ):
            self.run_pass()

        self.assertEqual((item.status, item.attempts), ("failed", 2))
        notify.assert_called_once()
        self.assertEqual(notify.call_args.args[1], item)

    def test_a_permanent_error_fails_the_item_at_once(self):
        def refuse(job, item):
            raise PermanentJobError("order code collision")

        self.handle_with(refuse)
        item = self.queue("a")

        with mute_logger(JOB_LOGGER):
            self.run_pass()

        self.assertEqual((item.status, item.attempts, item.last_error), ("failed", 1, "order code collision"))

    def test_a_failed_item_can_be_retried_by_hand(self):
        handled = self.record_handler()
        item = self.queue("a")
        item.write({"status": "failed", "attempts": 5, "last_error": "gave up"})

        item.action_retry()
        self.run_pass()

        self.assertEqual((item.status, handled), ("done", ["a"]))
