from datetime import datetime

from psycopg2 import IntegrityError

from odoo.fields import Domain
from odoo.tests import tagged
from odoo.tools import SQL, mute_logger

from .result_case import ResultCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE_BOOKING,
    MODEL_TESTING_FIGURE,
    MODEL_TESTING_FIGURE_PERIOD,
)
from odoo.addons.sol_laboratory.models.testing.testing_figure import PERIOD_FROM, PERIOD_TO

MEASURES = ("completed", "on_time", "turnaround_days", "overdue", "retests", "bookings", "booked_hours")
OCTOBER = ("2026-10-01", "2026-10-31")
DUE = datetime(2026, 10, 9, 17, 0)


@tagged("post_install", "-at_install")
class TestTestingFigures(ResultCase):
    """In October 2026, in UTC: the department approves lead on time after 4 days and holds a booking of an hour;
    Microbiology approves arsenic late after a retest; a third test stays open past its due date and a fourth is
    cancelled after it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.tz = "UTC"
        cls.arsenic = cls.add_test()
        cls.reception(cls.sample, datetime(2026, 10, 2, 8, 0))
        cls.due(cls.test, DUE)
        cls.due(cls.arsenic, DUE)
        lead = cls.enter()
        cls.sign(lead, datetime(2026, 10, 6, 8, 0))

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
        cls.sql(
            "UPDATE medilab_sample_test SET create_date = %s WHERE id IN %s",
            datetime(2026, 10, 1),
            (cls.test.id, cls.arsenic.id, cls.overdue.id, cls.cancelled.id),
        )
        cls.sql(
            "UPDATE medilab_sample_test SET cancelled_at = %s WHERE id = %s", datetime(2026, 10, 15), cls.cancelled.id
        )
        cls.env[MODEL_MACHINE_BOOKING].sudo().create(
            {
                "machine_id": cls.fast.id,
                "sample_test_id": cls.test.id,
                "task_id": cls.task.id,
                "person_id": cls.tester.id,
                "starts_at": datetime(2026, 10, 5, 8, 0),
                "ends_at": datetime(2026, 10, 5, 9, 0),
                "status": "done",
            }
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
        """The tester sends the result and the head approves it; both signatures are dated at the approval."""
        cls.send(result)
        cls.approve(result)
        cls.sql(
            "UPDATE medilab_signature SET create_date = %s WHERE document_model = %s AND document_id = %s",
            at,
            result._name,
            result.id,
        )

    def figures(self, period=OCTOBER, person=None, department=None):
        """The measures of the period by department, as the person reads them."""
        figures = self.env[MODEL_TESTING_FIGURE].with_context(**{PERIOD_FROM: period[0], PERIOD_TO: period[1]})
        if person:
            figures = figures.with_user(person.user_id)
        domain = Domain("department_id", "=", department.id) if department else Domain.TRUE
        aggregates = {name: f"{name}:{figures._fields[name].aggregator}" for name in MEASURES}
        groups = figures.formatted_read_group(domain, ["department_id"], list(aggregates.values()))
        return {
            group["department_id"][0]: {name: group[aggregate] for name, aggregate in aggregates.items()}
            for group in groups
            if group["department_id"]
        }

    def test_every_measure_of_each_department(self):
        figures = self.figures()

        self.assertEqual(
            figures[self.department.id],
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
        microbiology = figures[self.microbiology.id]
        self.assertEqual((microbiology["completed"], microbiology["on_time"]), (1, 0.0))
        self.assertAlmostEqual(microbiology["turnaround_days"], 10.0)
        self.assertEqual((microbiology["overdue"], microbiology["retests"], microbiology["bookings"]), (0, 1, 0))

    def test_a_test_finished_after_the_period_is_overdue_in_it(self):
        figures = self.figures(("2026-10-01", "2026-10-10"))

        # The cancelled test and the open one; arsenic, approved on 12 October, in Microbiology.
        self.assertEqual((figures[self.department.id]["overdue"], figures[self.department.id]["completed"]), (2, 1))
        self.assertEqual((figures[self.microbiology.id]["overdue"], figures[self.microbiology.id]["completed"]), (1, 0))
        self.assertEqual(figures[self.microbiology.id]["retests"], 1)

    def test_a_period_without_approvals_has_no_share_or_turnaround(self):
        figures = self.figures(("2026-11-01", "2026-11-30"))

        self.assertEqual(figures[self.department.id]["completed"], 0)
        self.assertFalse(figures[self.department.id]["on_time"])
        self.assertFalse(figures[self.department.id]["turnaround_days"])
        self.assertEqual(figures[self.department.id]["overdue"], 1)

    def test_a_head_reads_only_the_figures_of_their_department(self):
        self.grant(self.head, "testing_figure.read.own_department")

        figures = self.figures(person=self.head)

        self.assertEqual(set(figures), {self.department.id})
        self.assertFalse(self.figures(person=self.head, department=self.microbiology))

    def test_the_lab_head_filtering_a_department_reads_what_its_head_reads(self):
        lab_head = self.create_person("Vu Thi Lan", login="lan.vu", permissions=("testing_figure.read.all",))
        self.grant(self.head, "testing_figure.read.own_department")

        self.assertLessEqual({self.department.id, self.microbiology.id}, set(self.figures(person=lab_head)))
        self.assertEqual(self.figures(person=lab_head, department=self.department), self.figures(person=self.head))

    def test_a_period_ends_on_or_after_its_first_day(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.env[MODEL_TESTING_FIGURE_PERIOD].create({"date_from": "2026-10-31", "date_to": "2026-10-01"})

    def test_the_period_opens_the_figures_of_its_days(self):
        period = self.env[MODEL_TESTING_FIGURE_PERIOD].create({"date_from": OCTOBER[0], "date_to": OCTOBER[1]})

        action = period.action_show()

        self.assertEqual(action["context"], {PERIOD_FROM: OCTOBER[0], PERIOD_TO: OCTOBER[1]})
