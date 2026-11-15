from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBenchDemo(TransactionCase):
    """The demo data Medilab Mobile's testing at the bench opens: a testing task in progress whose method has steps,
    and results waiting for demo.head_of_department."""

    def test_the_tester_has_a_testing_task_in_progress_whose_method_has_steps(self):
        task = self.env.ref("sol_demo.demo_task_sample_test_lead_done")

        self.assertEqual(task.status, "in_progress")
        self.assertEqual(task.assignee_id, self.env.ref("sol_demo.demo_person_tester"))
        self.assertTrue(task.method_step_ids)

    def test_results_wait_for_the_head_one_of_them_entered_by_the_head(self):
        head = self.env.ref("sol_demo.demo_res_users_head_of_department")
        waiting = self.env.ref("sol_demo.demo_test_result_awaiting_head")
        by_head = self.env.ref("sol_demo.demo_test_result_by_head")

        for result in (waiting, by_head):
            with self.subTest(result=result.display_name):
                self.assertEqual(result.status, "requested")
                self.assertTrue(result.with_user(head).approval_can_sign)
        self.assertEqual(waiting.entered_by_id, self.env.ref("sol_demo.demo_res_users_tester"))
        self.assertEqual(by_head.entered_by_id, head)

    def test_a_result_sent_with_a_warning_shows_it_to_the_head(self):
        warned = self.env.ref("sol_demo.demo_test_result_warned")

        self.assertEqual(warned.status, "requested")
        self.assertIn("regulation limit", warned.check_warning or "")
