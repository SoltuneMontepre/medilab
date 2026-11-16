from odoo.exceptions import UserError
from odoo.tests import tagged

from .dispatch_case import DispatchCase
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE, MODEL_SAMPLE_TEST, MODEL_TASK, MODEL_TASK_TYPE
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_COLLECTION_CODE, SAMPLE_TEST_CODE


@tagged("post_install", "-at_install")
class TestSampleRecollection(DispatchCase):
    """The lead test of a received sample is outsourced, and its delivery to the subcontractor fails."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.department.manager_id = cls.head.employee_id
        cls.grant(cls.head, "sample.read.all", "sample.edit.all")
        cls.env[MODEL_TASK_TYPE].search([("code", "=", SAMPLE_COLLECTION_CODE)]).write(
            {"route": "role", "role_id": cls.delivery_role.id}
        )

    def failed_delivery(self):
        dispatch = self.send_dispatch(self.outsource())
        self.as_person(dispatch, self.head).action_cancel()
        return dispatch

    def testing_tasks(self):
        return self.env[MODEL_TASK].search(
            [
                ("type_id.code", "=", SAMPLE_TEST_CODE),
                ("document_model", "=", MODEL_SAMPLE_TEST),
                ("document_id", "in", self.sample.test_ids.ids),
            ]
        )

    def collection_tasks(self):
        return self.env[MODEL_TASK].search(
            [
                ("type_id.code", "=", SAMPLE_COLLECTION_CODE),
                ("document_model", "=", MODEL_SAMPLE),
                ("document_id", "=", self.sample.id),
            ]
        )

    def test_the_head_asks_for_the_same_sample_after_a_failed_delivery_and_it_waits_on_hold(self):
        self.failed_delivery()
        code, tests, tasks = self.sample.code, self.sample.test_ids, self.testing_tasks()
        sample = self.as_person(self.sample, self.head)

        self.assertTrue(sample.can_collect_again)
        sample.action_request_recollection()

        self.assertEqual(sample.status, "on_hold")
        self.assertEqual(sample.recollection_requested_by_id, self.head)
        self.assertEqual((sample.code, sample.test_ids, self.testing_tasks()), (code, tests, tasks))
        self.assertEqual(self.test.status, "outsourced")
        collection = self.collection_tasks()
        self.assertEqual(len(collection), 1)
        self.assertTrue(collection.with_user(self.courier.user_id).in_my_queue)
        self.assertFalse(sample.can_collect_again)

    def test_a_sample_received_again_goes_back_to_testing_with_no_new_testing_task(self):
        self.failed_delivery()
        self.as_person(self.sample, self.head).action_request_recollection()
        tasks = self.testing_tasks()

        self.as_person(self.sample, self.head).action_receive_more("1 L")

        self.assertEqual(self.sample.status, "testing")
        self.assertEqual(self.collection_tasks().status, "done")
        self.assertEqual(self.testing_tasks(), tasks)
        self.assertEqual(self.test.status, "outsourced")
        self.assertFalse(self.sample.can_collect_again)

    def test_a_dispatch_cancelled_before_it_is_sent_does_not_ask_for_the_sample_again(self):
        self.as_person(self.outsource(), self.head).action_cancel()
        sample = self.as_person(self.sample, self.head)

        self.assertFalse(sample.can_collect_again)
        with self.assertRaises(UserError):
            sample.action_request_recollection()
        self.assertEqual(sample.status, "testing")
