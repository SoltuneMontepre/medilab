from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from .dispatch_case import DispatchCase
from .scheduling_case import MONDAY


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestOutsourcedResultEntry(DispatchCase):
    def test_a_lab_qa_enters_an_outsourced_result_only_once_its_dispatch_is_sent(self):
        dispatch = self.outsource()

        self.assertFalse(self.as_person(self.test, self.tester).can_enter_result)
        with self.assertRaises(UserError):
            self.enter()

        self.send_dispatch(dispatch)

        self.assertTrue(self.as_person(self.test, self.tester).can_enter_result)
        self.assertEqual(self.enter().entered_by_id, self.tester.user_id)

    def test_the_subcontractor_result_waiting_to_be_sent_comes_before_a_lab_qa_result(self):
        result = self.enter_on_portal(self.send_dispatch(self.outsource()), "0.008")

        self.assertFalse(self.as_person(self.test, self.tester).can_enter_result)
        with self.assertRaises(UserError):
            self.enter()
        self.assertEqual(self.test.result_ids, result)
        self.assertTrue(result.is_reported)

    def test_a_lab_qa_enters_a_new_result_once_the_subcontractor_result_is_rejected(self):
        result = self.enter_on_portal(self.send_dispatch(self.outsource()), "0.008")
        self.send_portal_result(result)
        self.as_person(result, self.head).action_reject("The blank was contaminated.")

        self.assertTrue(self.as_person(self.test, self.tester).can_enter_result)
        self.assertEqual(self.enter().attempt, 2)
