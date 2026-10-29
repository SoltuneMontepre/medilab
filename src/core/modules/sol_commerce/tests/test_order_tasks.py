from odoo.exceptions import UserError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_laboratory.constants.models import MODEL_TASK

QUOTATION_TASK_TYPE = "sol_commerce.task_type_order_quotation"


@tagged("post_install", "-at_install")
class TestOrderTasks(OrderCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref(QUOTATION_TASK_TYPE).role_id = cls.sales_person.role_ids

    def submitted_order(self):
        order = self.make_order([(self.lead_product, 1)], advance_method="cash", advance_mode="full")
        order.action_submit()
        return order

    def task_of(self, document):
        return self.env[MODEL_TASK].search([("document_model", "=", document._name), ("document_id", "=", document.id)])

    def queue_of(self, user):
        return self.env[MODEL_TASK].with_user(user).search([("in_my_queue", "=", True)])

    def test_submitted_order_waits_in_the_sales_queue(self):
        order = self.submitted_order()
        task = self.task_of(order)

        self.assertEqual(task.type_id, self.env.ref(QUOTATION_TASK_TYPE))
        self.assertEqual(task.status, "open")
        self.assertFalse(task.assignee_id)
        self.assertTrue(task.deadline)
        self.assertIn(task, self.queue_of(self.sales))
        self.assertIn(task, self.queue_of(self.other_sales))

    def test_claiming_the_order_assigns_its_task(self):
        order = self.submitted_order()
        task = self.task_of(order)

        order.with_user(self.sales).action_claim()

        self.assertEqual(task.assignee_id, self.sales_person)
        self.assertEqual(task.status, "assigned")
        self.assertNotIn(task, self.queue_of(self.other_sales))
        self.assertIn(task, self.env[MODEL_TASK].with_user(self.sales).search([("is_mine", "=", True)]))

    def test_claiming_the_task_claims_the_order(self):
        order = self.submitted_order()
        task = self.task_of(order)

        task.with_user(self.other_sales).action_claim()

        self.assertEqual(order.user_id, self.other_sales)
        self.assertEqual(order.order_status, "claimed")
        self.assertEqual(task.assignee_id, self.other_person)
        with self.assertRaises(UserError):
            task.with_user(self.sales).action_claim()
        with self.assertRaises(UserError):
            order.with_user(self.sales).action_claim()

    def test_sending_the_quotation_closes_the_task(self):
        order = self.submitted_order()
        task = self.task_of(order)
        order.with_user(self.sales).action_claim()
        order._catalog_lines().sample_id = self.make_sample(order)

        order.with_user(self.sales).action_send_quotation()

        self.assertEqual(task.status, "done")
        self.assertFalse(self.task_of(order.sudo().invoice_ids), "An advance invoice is posted, so nobody posts it.")

    def test_cancelling_the_order_cancels_the_task(self):
        order = self.submitted_order()
        task = self.task_of(order)

        order.with_user(self.portal).action_customer_cancel()

        self.assertEqual(task.status, "cancelled")

    def test_changing_the_salesperson_moves_the_task(self):
        order = self.submitted_order()
        task = self.task_of(order)
        order.with_user(self.sales).action_claim()

        order.with_user(self.head).user_id = self.other_sales

        self.assertEqual(task.assignee_id, self.other_person)
        self.assertTrue(task.reassign_reason)

    def test_an_order_sales_creates_has_no_queue_task(self):
        order = self.make_order([(self.lead_product, 1)], status="claimed", user_id=self.sales.id)

        self.assertFalse(self.task_of(order))
