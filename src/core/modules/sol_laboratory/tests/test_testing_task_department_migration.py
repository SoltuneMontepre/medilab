from pathlib import Path

from freezegun import freeze_time

from odoo.modules.module import load_script
from odoo.tests import tagged

from .scheduling_case import MONDAY, SchedulingCase
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST

POST_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.61.0" / "post-migrate.py"


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestTestingTaskDepartmentMigration(SchedulingCase):
    """Lead testing tasks of the received sample were moved to Microbiology before a testing task had to stay in the
    department of its way of testing."""

    def misplaced(self, assignee=None, status="open"):
        """A lead testing task in Microbiology, as an earlier move left it."""
        test = self.env[MODEL_SAMPLE_TEST].create({"sample_id": self.sample.id, "parameter_id": self.parameter.id})
        task = self.testing_task(test)
        # As the moves before the rule wrote it, past its check.
        self.env.cr.execute(
            "UPDATE medilab_task SET department_id = %s, assignee_id = %s, status = %s WHERE id = %s",
            (self.microbiology.id, assignee.id if assignee else None, status, task.id),
        )
        self.env.invalidate_all()
        return task

    def migrate(self):
        load_script(str(POST_MIGRATE), "post_migrate").migrate(self.env.cr, "20.0.1.60.0")
        self.env.invalidate_all()

    def test_a_queued_testing_task_returns_to_the_department_of_its_way(self):
        task = self.misplaced()

        self.migrate()

        self.assertEqual((task.department_id, task.status), (self.department, "open"))
        self.assertTrue(task.reassign_reason)

    def test_a_testing_task_assigned_outside_the_department_of_its_way_returns_to_its_queue(self):
        self.authorize(self.microbiologist, self.parameter)
        task = self.misplaced(self.microbiologist, "assigned")

        self.migrate()

        self.assertEqual((task.department_id, task.status), (self.department, "open"))
        self.assertFalse(task.assignee_id)

    def test_a_testing_task_assigned_to_an_authorized_tester_of_its_department_keeps_them(self):
        task = self.misplaced(self.tester, "assigned")

        self.migrate()

        self.assertEqual(
            (task.department_id, task.assignee_id, task.status), (self.department, self.tester, "assigned")
        )

    def test_a_testing_task_in_progress_with_a_tester_of_its_department_returns_and_goes_on(self):
        task = self.misplaced(self.tester, "in_progress")

        self.migrate()

        self.assertEqual(
            (task.department_id, task.assignee_id, task.status), (self.department, self.tester, "in_progress")
        )

    def test_a_testing_task_in_progress_outside_the_department_of_its_way_returns_to_its_queue(self):
        self.authorize(self.microbiologist, self.parameter)
        task = self.misplaced(self.microbiologist, "in_progress")

        self.migrate()

        self.assertEqual((task.department_id, task.status), (self.department, "open"))
        self.assertFalse(task.assignee_id)

    def test_a_finished_testing_task_stays_where_it_is(self):
        task = self.misplaced(self.microbiologist, "done")

        self.migrate()

        self.assertEqual((task.department_id, task.status), (self.microbiology, "done"))
