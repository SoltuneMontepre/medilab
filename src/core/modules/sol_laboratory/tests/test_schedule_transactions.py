import logging
from unittest.mock import patch

from odoo.tests import tagged

from .scheduling_concurrency_case import SchedulingConcurrencyCase
from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING, MODEL_SAMPLE_TEST, MODEL_TASK

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestScheduleTransactions(SchedulingConcurrencyCase):
    """A schedule request that fails while it synchronizes the booking's calendar and room events commits nothing of
    itself, and the next schedule of the test succeeds."""

    def setUp(self):
        super().setUp()
        self.committed(self.assign)
        self.committed(self.keep_foreign_queue)
        self.before = self.committed(self.graph)
        self.counts = self.committed(self.table_counts)

    def schedule(self, env):
        env[MODEL_SAMPLE_TEST].browse(self.test_ids[0]).with_user(self.user_ids[0]).action_schedule()

    def failing(self, model, method, condition):
        """Patch the method of the model to raise a RuntimeError with a message no other code raises, once, when the
        condition holds before it runs; the condition returns what the transaction had written by then, kept in
        self.injected."""
        model_class = type(self.env[model])
        real_method = getattr(model_class, method)
        self.injected = []
        self.injected_message = f"Injected failure {model}.{method} {self.token}"

        def call(records, *args, **kwargs):
            if not self.injected and (written := condition(records, args)):
                self.injected.append(written)
                _logger.info("Injected failure %s.%s after writing %s", model, method, written)
                raise RuntimeError(self.injected_message)
            return real_method(records, *args, **kwargs)

        return patch.object(model_class, method, call)

    def assert_rolled_back(self, outcome):
        self.assertEqual(outcome[0], "failed", outcome)
        self.assertIs(type(outcome[1]), RuntimeError, outcome)
        self.assertEqual(str(outcome[1]), self.injected_message)
        self.assertEqual(len(self.injected), 1)
        self.assertEqual(self.committed(self.graph), self.before)
        self.assertEqual(self.committed(self.table_counts), self.counts)
        self.committed(self.assert_committed_invariants)

    def assert_recovers(self):
        self.assertEqual(self.request(self.schedule)[0], "committed")
        graph = self.committed(self.graph)
        self.assert_consistent_booking(graph, 0)
        self.committed(self.assert_committed_invariants)

    def test_a_schedule_failing_before_its_rooms_are_booked_commits_nothing(self):
        test_id = self.test_ids[0]

        def placed(bookings, _args):
            if bookings.status == "scheduled" and bookings.sample_test_id.id == test_id:
                return {"booking": bookings.id, "status": bookings.status, "starts_at": bookings.starts_at}
            return None

        with self.failing(MODEL_MACHINE_BOOKING, "_sync_room_events", placed):
            outcome = self.request(self.schedule)

        [written] = self.injected
        self.assertTrue(written["starts_at"], written)
        self.assert_rolled_back(outcome)
        self.assert_recovers()

    def test_a_schedule_failing_after_its_calendar_and_rooms_are_booked_commits_nothing(self):
        task_id = self.task_ids[0]

        def planning(tasks, args):
            if tasks.ids == [task_id] and args[0].get("planned_start"):
                booking = tasks.booking_ids.filtered(lambda booking: booking.status == "scheduled")
                return {
                    "booking": booking.id,
                    "person_event": booking.calendar_event_id.id,
                    "room_events": booking.room_event_ids.ids,
                }
            return None

        with self.failing(MODEL_TASK, "write", planning):
            outcome = self.request(self.schedule)

        [written] = self.injected
        self.assertTrue(written["person_event"], written)
        self.assertEqual(len(written["room_events"]), 1, written)
        self.assert_rolled_back(outcome)
        self.assert_recovers()
