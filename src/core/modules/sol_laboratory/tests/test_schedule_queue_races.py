import logging
import uuid
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .scheduling_concurrency_case import NAMES, RETRIED_CONFLICTS, SchedulingConcurrencyCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_CALENDAR_EVENT,
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_SAMPLE_TEST,
)

_logger = logging.getLogger(__name__)
FIXTURE_FIELDS = (
    "token",
    "department_id",
    "person_ids",
    "user_ids",
    "partner_ids",
    "logins",
    "machine_id",
    "room_id",
    "test_ids",
    "task_ids",
)
WRITE_STAMP = ("write_uid", "write_date")


@tagged("post_install", "-at_install")
class TestScheduleQueueRaces(SchedulingConcurrencyCase):
    """Two departments, each with its own tester, machine and room, schedule at once through the real global queue.

    A third department of the fixture holds a queued booking that no machine can place, so every replan of the queue
    meets it. Other tests' queued bookings stay in the queue too and are put back as they were. No fairness or
    department isolation is assumed; whether one department's replan may touch another's bookings is open (Q-scope)."""

    def setUp(self):
        super().setUp()
        self.departments = [self.fixture()]
        for _number in range(2):
            self.token = uuid.uuid4().hex[:12]
            self.committed(self.prepare)
            self.departments.append(self.fixture())
        self.holder = self.departments.pop()

        def assign(env):
            for department in self.departments:
                self.use(department)
                self.assign(env)

        self.committed(assign)
        self.held_ids = self.committed(self.hold_queue)
        self.held_before = self.committed(lambda env: self.foreign_rows(env, self.held_ids))
        self.foreign_ids, self.foreign_before = self.committed(self.keep_foreign_queue)
        self.before = [self.department_graph(department) for department in self.departments]

    def fixture(self):
        return {name: getattr(self, name) for name in FIXTURE_FIELDS}

    def use(self, department):
        """Point the fixture's ids at the department, for the helpers that read them."""
        self.__dict__.update(department)

    def department_graph(self, department):
        self.use(department)
        return self.committed(self.graph)

    def hold_queue(self, env):
        """The holding department schedules its first test, then its only machine goes under repair: the booking goes
        back to the queue, where no machine can place it. Returns the booking's and its test's ids, by table."""
        self.use(self.holder)
        self.assign(env)
        test = env[MODEL_SAMPLE_TEST].browse(self.test_ids[0])
        test.with_user(self.user_ids[0]).action_schedule()
        booking = test.booking_ids
        # The repair deletes the booking's events; owning them lets the cleanup remove the audit rows of the deletion.
        self.owned.setdefault(MODEL_CALENDAR_EVENT, []).extend((booking.calendar_event_id | booking.room_event_ids).ids)
        env[MODEL_MACHINE].browse(self.machine_id).status = "under_repair"
        self.assertEqual((booking.status, booking.starts_at, booking.ends_at), ("queued", False, False))
        self.assertFalse(booking.calendar_event_id | booking.room_event_ids)
        self.assertTrue(test.outsourcing_suggested)
        self.assertIsNone(booking._recommend(test, booking.person_id, booking.department_id))
        self.assert_committed_invariants(env)
        return {"medilab_machine_booking": booking.ids, "medilab_sample_test": test.ids}

    def schedule(self, number):
        department = self.departments[number]

        def action(env):
            test = env[MODEL_SAMPLE_TEST].browse(department["test_ids"][0])
            test.with_user(department["user_ids"][0]).action_schedule()

        return action

    def queueing(self, number):
        """The department's first test's booking is about to be created."""
        test_id = self.departments[number]["test_ids"][0]
        return (
            MODEL_MACHINE_BOOKING,
            "create",
            lambda _bookings, args: any(values.get("sample_test_id") == test_id for values in self.values(args[0])),
        )

    def refusing(self, number):
        """The department's booking is about to book its rooms, after the queue was replanned: refuse it with a message
        no other code raises. Returns the message; self.refused lists the bookings refused."""
        test_id = self.departments[number]["test_ids"][0]
        message = f"Injected refusal {self.token}"
        model_class = type(self.env[MODEL_MACHINE_BOOKING])
        real_method = model_class._sync_room_events
        self.refused = []

        def call(booking):
            if booking.status == "scheduled" and booking.sample_test_id.id == test_id:
                self.refused.append(booking.id)
                raise UserError(message)
            return real_method(booking)

        self.enterContext(patch.object(model_class, "_sync_room_events", call))
        return message

    def race_departments(self, commits_first=None):
        outcomes = self.race(
            self.schedule(0),
            self.schedule(1),
            boundaries={"first": self.queueing(0), "second": self.queueing(1)},
            commits_first=commits_first,
        )
        effects = self.committed(
            lambda env: (self.foreign_rows(env, self.held_ids), self.foreign_rows(env, self.foreign_ids))
        )
        _logger.info(
            "Global queue %s: held rows before %s after %s; other queued rows before %s after %s",
            self._testMethodName,
            self.held_before,
            effects[0],
            self.foreign_before,
            effects[1],
        )
        return outcomes, effects

    def assert_retries_were_conflicts(self):
        """Every attempt but the last of each thread failed on a database conflict that request retrying retries."""
        evidence = self.race_evidence
        for name in NAMES:
            conflicts = evidence["conflicts"][name]
            self.assertLessEqual(set(conflicts), RETRIED_CONFLICTS, evidence)
            self.assertEqual(evidence["attempts"][name], len(conflicts) + 1, evidence)

    def assert_queue_kept(self, effects):
        """The held booking and other tests' queued bookings are still queued with no slot, and their tests still
        suggested for outsourcing with their way of testing; when and by whom their rows were last written is not
        checked."""

        def content(rows):
            return {
                table: {
                    row_id: {column: value for column, value in values.items() if column not in WRITE_STAMP}
                    for row_id, values in table_rows.items()
                }
                for table, table_rows in rows.items()
            }

        held, foreign = effects
        self.assertEqual(content(held), content(self.held_before))
        self.assertEqual(content(foreign), content(self.foreign_before))
        self.use(self.holder)
        self.committed(self.assert_committed_invariants)

    def assert_scheduled(self, number):
        graph = self.department_graph(self.departments[number])
        self.assert_consistent_booking(graph, 0)
        self.assertEqual(len(graph["bookings"]), 1, graph)
        self.assertEqual(
            (graph["tasks"][1], graph["tests"][1]), (self.before[number]["tasks"][1], self.before[number]["tests"][1])
        )
        self.committed(self.assert_committed_invariants)

    def assert_both_committed(self, outcomes):
        self.assertEqual({name: outcome[0] for name, outcome in outcomes.items()}, dict.fromkeys(outcomes, "committed"))
        self.assert_retries_were_conflicts()
        for number in (0, 1):
            self.assert_scheduled(number)

    def test_two_departments_scheduling_at_once_both_commit_when_the_first_commits_first(self):
        outcomes, effects = self.race_departments(commits_first="first")

        self.assert_both_committed(outcomes)
        self.assert_queue_kept(effects)

    def test_two_departments_scheduling_at_once_both_commit_when_the_second_commits_first(self):
        outcomes, effects = self.race_departments(commits_first="second")

        self.assert_both_committed(outcomes)
        self.assert_queue_kept(effects)

    def test_two_departments_scheduling_at_once_both_commit_in_either_order(self):
        outcomes, effects = self.race_departments()

        self.assert_both_committed(outcomes)
        self.assert_queue_kept(effects)

    def test_a_department_refused_after_its_replan_leaves_the_other_departments_schedule_committed(self):
        message = self.refusing(1)

        outcomes, effects = self.race_departments()

        self.assertEqual(outcomes["first"][0], "committed", outcomes)
        self.assertEqual(outcomes["second"], ("refused", message))
        self.assertEqual(len(self.refused), 1, "The refusal was not injected exactly once")
        self.assert_retries_were_conflicts()
        self.assert_scheduled(0)
        self.assertEqual(self.department_graph(self.departments[1]), self.before[1])
        self.committed(self.assert_committed_invariants)
        self.assert_queue_kept(effects)
