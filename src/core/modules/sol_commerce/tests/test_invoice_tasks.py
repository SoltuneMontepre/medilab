from odoo.fields import Command
from odoo.tests import tagged

from .invoicing_case import InvoicingCase
from odoo.addons.sol_laboratory.constants.models import MODEL_PERSON, MODEL_ROLE, MODEL_TASK

POSTING_TASK_TYPE = "sol_commerce.task_type_invoice_posting"


@tagged("post_install", "-at_install")
class TestInvoiceTasks(InvoicingCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        role = cls.env[MODEL_ROLE].create({"code": "posting_accountant", "name": "Accountant"})
        cls.env.ref(POSTING_TASK_TYPE).role_id = role
        accountant = cls.env[MODEL_PERSON].create({"name": "Vo Thi Lan", "login": "posting.accountant"})
        accountant.role_ids = role
        cls.accountant = accountant.user_id
        cls.accountant.write({"group_ids": [Command.link(cls.env.ref("account.group_account_invoice").id)]})
        cls.sales = cls.env[MODEL_PERSON].create({"name": "Nguyen Thi Thu", "login": "posting.sales"}).user_id

    def task_of(self, invoice):
        return self.env[MODEL_TASK].search([("document_model", "=", invoice._name), ("document_id", "in", invoice.ids)])

    def sales_draft(self):
        # Sales drafts an invoice with full rights, as the order's Create invoices dialog does.
        return self.order.with_user(self.sales).sudo().create_final_invoice()

    def test_an_invoice_sales_drafts_waits_for_the_accountant(self):
        draft = self.sales_draft()
        task = self.task_of(draft)

        self.assertEqual(task.type_id, self.env.ref(POSTING_TASK_TYPE))
        self.assertEqual(task.status, "open")
        self.assertTrue(task.deadline)
        self.assertIn(task, self.env[MODEL_TASK].with_user(self.accountant).search([("in_my_queue", "=", True)]))

        draft.with_user(self.accountant).action_post()

        self.assertEqual(task.status, "done")

    def test_an_invoice_the_accountant_drafts_has_no_task(self):
        draft = self.order.with_user(self.accountant).sudo().create_final_invoice()

        self.assertFalse(self.task_of(draft))

    def test_cancelling_the_invoice_cancels_its_task(self):
        draft = self.sales_draft()
        task = self.task_of(draft)

        draft.button_cancel()

        self.assertEqual(task.status, "cancelled")
