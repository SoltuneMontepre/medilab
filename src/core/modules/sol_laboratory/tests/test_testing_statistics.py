from datetime import datetime
from types import SimpleNamespace

from psycopg2 import IntegrityError

from odoo.fields import Domain
from odoo.tests import tagged
from odoo.tools import SQL, mute_logger

from .result_case import ResultCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE_BOOKING,
    MODEL_TESTING_STATISTIC,
    MODEL_TESTING_STATISTIC_PERIOD,
)
from odoo.addons.sol_laboratory.constants.statistics import STATISTICS_FROM, STATISTICS_TO

MEASURES = ("completed", "on_time", "turnaround_days", "overdue", "retests", "bookings", "booked_hours")
OCTOBER = ("2026-10-01", "2026-10-31")
NOVEMBER = ("2026-11-01", "2026-11-30")
DUE = datetime(2026, 10, 9, 17, 0)
REACHED = datetime(2026, 10, 1)


@tagged("post_install", "-at_install")
class TestTestingStatistics(ResultCase):
    """In October 2026, in UTC: the department approves lead on time after 4 days and holds a booking of an hour;
    Microbiology approves arsenic late after a retest; a third test stays open past its due date and a fourth is
    cancelled after it. A fifth test is due too, but its sample never reached a department."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.tz = "UTC"
        cls.arsenic = cls.add_test()
        cls.reception(cls.sample, datetime(2026, 10, 2, 8, 0))
        cls.due(cls.test, DUE)
        cls.due(cls.arsenic, DUE)
        cls.lead = cls.enter()
        cls.sign(cls.lead, datetime(2026, 10, 6, 8, 0))

        rejected = cls.enter(test=cls.arsenic)
        cls.send(rejected)
        cls.as_person(rejected, cls.head).action_reject("The blank read above the limit of detection.")
        cls.entered(rejected, datetime(2026, 10, 3, 8, 0))
        cls.as_person(cls.arsenic._testing_task(), cls.tester).action_claim()
        retest = cls.enter(test=cls.arsenic)
        cls.entered(retest, datetime(2026, 10, 8, 8, 0))
        cls.sign(retest, datetime(2026, 10, 12, 8, 0))
        # Finished tasks cannot be moved, so Microbiology takes arsenic over in the database.
        cls.sql(
            "UPDATE medilab_task SET department_id = %s WHERE document_model = %s AND document_id = %s",
            cls.microbiology.id,
            cls.arsenic._name,
            cls.arsenic.id,
        )

        cls.overdue = cls.new_test(DUE)
        cls.testing_task(cls.overdue, cls.tester)
        cls.cancelled = cls.new_test(DUE)
        cls.testing_task(cls.cancelled, cls.tester)
        cls.as_person(cls.cancelled, cls.head).action_cancel("The bottle leaked.")
        cls.unreached = cls.new_test(DUE)
        tests = (cls.test.id, cls.arsenic.id, cls.overdue.id, cls.cancelled.id, cls.unreached.id)
        cls.sql("UPDATE medilab_sample_test SET create_date = %s WHERE id IN %s", REACHED, tests)
        # Each test reached its department on the first day.
        cls.sql(
            "UPDATE medilab_task SET create_date = %s WHERE document_model = %s AND document_id IN %s",
            REACHED,
            cls.test._name,
            tests,
        )
        cls.sql(
            "UPDATE medilab_sample_test SET cancelled_at = %s WHERE id = %s", datetime(2026, 10, 15), cls.cancelled.id
        )
        cls.booking(datetime(2026, 10, 5, 8, 0), "done")

    @classmethod
    def booking(cls, starts_at, status):
        """An hour's booking of lead by the tester."""
        return (
            cls.env[MODEL_MACHINE_BOOKING]
            .sudo()
            .create(
                {
                    "machine_id": cls.fast.id,
                    "sample_test_id": cls.test.id,
                    "task_id": cls.task.id,
                    "person_id": cls.tester.id,
                    "starts_at": starts_at,
                    "ends_at": starts_at.replace(hour=starts_at.hour + 1),
                    "status": status,
                }
            )
        )

    @classmethod
    def sql(cls, query, *args):
        """Date records in the database, after the writes still pending, which would overwrite it."""
        cls.env.flush_all()
        cls.env.cr.execute(SQL(query, *args))
        cls.env.invalidate_all()

    @classmethod
    def reception(cls, sample, at):
        cls.sql("UPDATE medilab_sample SET received_at = %s WHERE id = %s", at, sample.id)

    @classmethod
    def due(cls, test, at):
        cls.sql("UPDATE medilab_sample_test SET due_date = %s WHERE id = %s", at, test.id)

    @classmethod
    def entered(cls, result, at):
        cls.sql("UPDATE medilab_test_result SET entered_at = %s WHERE id = %s", at, result.id)

    @classmethod
    def sign(cls, result, at):
        """The tester sends the result and the head approves it; both signatures and the test's first approval are
        dated at the approval."""
        cls.send(result)
        cls.approve(result)
        cls.sql(
            "UPDATE medilab_signature SET create_date = %s WHERE document_model = %s AND document_id = %s",
            at,
            result._name,
            result.id,
        )
        cls.sql("UPDATE medilab_sample_test SET first_approved_at = %s WHERE id = %s", at, result.sample_test_id.id)

    def statistics(self, period=OCTOBER, person=None, department=None):
        """The measures of the period by department, as the person reads them."""
        rows = self.env[MODEL_TESTING_STATISTIC].with_context(**{STATISTICS_FROM: period[0], STATISTICS_TO: period[1]})
        if person:
            rows = rows.with_user(person.user_id)
        domain = Domain("department_id", "=", department.id) if department else Domain.TRUE
        aggregates = {name: f"{name}:{rows._fields[name].aggregator}" for name in MEASURES}
        groups = rows.formatted_read_group(domain, ["department_id"], list(aggregates.values()))
        return {
            group["department_id"][0]: {name: group[aggregate] for name, aggregate in aggregates.items()}
            for group in groups
            if group["department_id"]
        }

    def test_every_measure_of_each_department(self):
        statistics = self.statistics()

        self.assertEqual(
            statistics[self.department.id],
            {
                "completed": 1,
                "on_time": 100.0,
                "turnaround_days": 4.0,
                "overdue": 1,
                "retests": 0,
                "bookings": 1,
                "booked_hours": 1.0,
            },
        )
        microbiology = statistics[self.microbiology.id]
        self.assertEqual((microbiology["completed"], microbiology["on_time"]), (1, 0.0))
        self.assertAlmostEqual(microbiology["turnaround_days"], 10.0)
        self.assertEqual((microbiology["overdue"], microbiology["retests"], microbiology["bookings"]), (0, 1, 0))

    def test_a_test_finished_after_the_period_is_overdue_in_it(self):
        statistics = self.statistics(("2026-10-01", "2026-10-10"))

        # The cancelled test and the open one; arsenic, approved on 12 October, in Microbiology.
        self.assertEqual(
            (statistics[self.department.id]["overdue"], statistics[self.department.id]["completed"]), (2, 1)
        )
        self.assertEqual(
            (statistics[self.microbiology.id]["overdue"], statistics[self.microbiology.id]["completed"]), (1, 0)
        )
        self.assertEqual(statistics[self.microbiology.id]["retests"], 1)

    def test_a_test_whose_sample_reached_no_department_is_never_overdue(self):
        rows = self.env[MODEL_TESTING_STATISTIC].with_context(
            **{STATISTICS_FROM: OCTOBER[0], STATISTICS_TO: OCTOBER[1]}
        )

        self.assertFalse(rows.search_count([("sample_test_id", "=", self.unreached.id)]))

    def test_a_period_without_approvals_has_no_share_or_turnaround(self):
        statistics = self.statistics(NOVEMBER)

        self.assertEqual(statistics[self.department.id]["completed"], 0)
        self.assertFalse(statistics[self.department.id]["on_time"])
        self.assertFalse(statistics[self.department.id]["turnaround_days"])
        self.assertEqual(statistics[self.department.id]["overdue"], 1)

    def test_sending_a_result_back_leaves_its_first_approval_in_its_period(self):
        october, november = self.statistics(), self.statistics(NOVEMBER)

        self.lead._send_back("Check the blank again.")

        self.assertEqual(self.test.first_approved_at, datetime(2026, 10, 6, 8, 0))
        self.assertEqual(self.statistics(), october)
        self.assertEqual(self.statistics(NOVEMBER), november)

    def test_a_correction_is_no_retest_and_leaves_the_first_approval(self):
        october = self.statistics()

        version = self.lead._new_version(SimpleNamespace(requested_change="Report the value in µg/L."))

        self.assertEqual(version.replaces_id, self.lead)
        self.assertEqual(self.statistics(), october)
        self.assertEqual(self.statistics(NOVEMBER)[self.department.id]["retests"], 0)

    def test_a_cancelled_booking_is_no_workload(self):
        self.booking(datetime(2026, 10, 20, 8, 0), "cancelled")

        self.assertEqual(self.statistics()[self.department.id]["bookings"], 1)

    def test_a_test_cancelled_with_its_request_keeps_when(self):
        test = self.new_test(DUE)

        test.sample_id.request_id.action_cancel()

        self.assertEqual(test.status, "cancelled")
        self.assertTrue(test.cancelled_at)

    def test_a_head_reads_only_the_statistics_of_their_department(self):
        self.grant(self.head, "testing_statistic.read.own_department")

        statistics = self.statistics(person=self.head)

        self.assertEqual(set(statistics), {self.department.id})
        self.assertFalse(self.statistics(person=self.head, department=self.microbiology))

    def test_the_lab_head_filtering_a_department_reads_what_its_head_reads(self):
        lab_head = self.create_person("Vu Thi Lan", login="lan.vu", permissions=("testing_statistic.read.all",))
        self.grant(self.head, "testing_statistic.read.own_department")

        self.assertLessEqual({self.department.id, self.microbiology.id}, set(self.statistics(person=lab_head)))
        self.assertEqual(
            self.statistics(person=lab_head, department=self.department), self.statistics(person=self.head)
        )

    def test_a_period_ends_on_or_after_its_first_day(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.env[MODEL_TESTING_STATISTIC_PERIOD].create({"date_from": "2026-10-31", "date_to": "2026-10-01"})

    def test_the_period_opens_the_statistics_of_its_days(self):
        period = self.env[MODEL_TESTING_STATISTIC_PERIOD].create({"date_from": OCTOBER[0], "date_to": OCTOBER[1]})

        action = period.action_show()

        self.assertEqual(action["context"], {STATISTICS_FROM: OCTOBER[0], STATISTICS_TO: OCTOBER[1]})
