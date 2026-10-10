from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .task_case import TaskCase


@tagged("post_install", "-at_install")
class TestTaskDashboard(TaskCase):
    def dashboard(self, person):
        return self.as_person(self.tasks, person).get_dashboard_data()

    def test_dashboard_shows_the_person_open_tasks_overdue_first(self):
        later = self.create_by_hand(self.chemist)
        overdue = self.create_by_hand(self.chemist, deadline=fields.Datetime.now() - timedelta(hours=2))
        self.create_by_hand(self.microbiologist)

        data = self.dashboard(self.chemist)
        self.assertEqual((data["open_count"], data["overdue_count"]), (2, 1))
        self.assertEqual([task["id"] for task in data["next_up"]], [overdue.id, later.id])

    def test_dashboard_shows_today_plan_and_finished_work(self):
        now = fields.Datetime.now()
        planned = self.create_by_hand(self.chemist, planned_start=now, planned_end=now + timedelta(hours=1))
        done = self.create_by_hand(self.chemist)
        self.as_person(done, self.chemist).action_done()

        data = self.dashboard(self.chemist)
        self.assertIn(planned.id, [task["id"] for task in data["planned_today"]])
        self.assertEqual((data["finished_count"], data["finished_week_count"]), (1, 1))

    def test_dashboard_lists_the_tasks_the_person_can_claim(self):
        own = self.receive_sample(self.chemistry)
        self.receive_sample(self.microbiology)

        data = self.dashboard(self.chemist)
        self.assertEqual(data["claimable_count"], 1)
        self.assertEqual([task["id"] for task in data["claimable"]], [own.id])
