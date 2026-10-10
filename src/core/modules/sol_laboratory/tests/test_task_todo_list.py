from odoo.tests import tagged

from .task_case import TaskCase


@tagged("post_install", "-at_install")
class TestTaskTodoList(TaskCase):
    def todo(self, person):
        return self.as_person(self.tasks, person).search(
            [("is_mine", "=", True), ("status", "in", ("assigned", "in_progress"))]
        )

    def test_assigned_task_appears_in_the_assignee_todo_list_with_its_deadline(self):
        task = self.create_by_hand(self.chemist)

        self.assertEqual(self.todo(self.chemist), task)
        self.assertEqual(self.as_person(task, self.chemist).deadline, self.tomorrow)
        self.assertFalse(self.todo(self.microbiologist))

    def test_todo_list_shows_the_soonest_deadline_first(self):
        later = self.create_by_hand(self.chemist, deadline=self.tomorrow.replace(year=self.tomorrow.year + 1))
        sooner = self.create_by_hand(self.chemist)

        self.assertEqual(self.todo(self.chemist).ids, [sooner.id, later.id])

    def test_done_task_moves_to_the_completed_list(self):
        task = self.create_by_hand(self.chemist)

        self.as_person(task, self.chemist).action_done()
        self.assertFalse(self.todo(self.chemist))
        completed = self.as_person(self.tasks, self.chemist).search([("is_mine", "=", True), ("status", "=", "done")])
        self.assertEqual(completed, task)

    def test_person_reads_only_their_own_tasks_and_their_queue(self):
        mine = self.create_by_hand(self.chemist)
        others = self.create_by_hand(self.microbiologist)
        queued = self.receive_sample(self.chemistry)

        self.assertEqual(self.as_person(self.tasks, self.chemist).search([]), mine | queued)
        self.assertNotIn(others, self.as_person(self.tasks, self.chemist).search([]))

    def test_user_without_a_person_has_no_tasks_of_their_own(self):
        self.receive_sample(self.chemistry)
        user = self.env["res.users"].create({"name": "Odoo only", "login": "odoo.only"})

        self.assertFalse(self.tasks.with_user(user).sudo().search([("is_mine", "=", True)]))
