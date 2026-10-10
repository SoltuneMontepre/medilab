import re
from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .invoicing_case import InvoicingCase
from odoo.addons.commerce.constants.models import MODEL_INVOICE
from odoo.addons.laboratory.constants.models import MODEL_IR_SEQUENCE, MODEL_RES_CONFIG_SETTINGS

NUMBER = re.compile(r"^\d{4} \d{2}/HD$")


@tagged("post_install", "-at_install")
class TestInvoicePosting(InvoicingCase):
    def test_posting_numbers_the_invoice_and_sets_its_due_date(self):
        invoice = self.create_invoice(post=False)
        self.assertFalse(invoice.code)

        invoice.action_post()

        self.assertRegex(invoice.code, NUMBER)
        self.assertEqual(invoice.status, "posted")
        self.assertEqual(invoice.due_date, fields.Date.context_today(invoice) + timedelta(days=7))

    def test_the_due_days_come_from_the_settings(self):
        settings = self.env[MODEL_RES_CONFIG_SETTINGS].create({"invoice_due_days": 10})
        settings.set_values()

        invoice = self.create_invoice()

        self.assertEqual(invoice.due_date, fields.Date.context_today(invoice) + timedelta(days=10))

    def test_numbers_restart_each_year(self):
        sequence = self.env[MODEL_IR_SEQUENCE]
        first_2027 = sequence.next_by_code(MODEL_INVOICE, sequence_date=date(2027, 1, 5))
        second_2027 = sequence.next_by_code(MODEL_INVOICE, sequence_date=date(2027, 6, 5))
        first_2028 = sequence.next_by_code(MODEL_INVOICE, sequence_date=date(2028, 1, 5))

        self.assertEqual((first_2027, second_2027, first_2028), ("0001 27/HD", "0002 27/HD", "0001 28/HD"))

    def test_an_invoice_without_lines_is_not_posted(self):
        invoice = self.env[MODEL_INVOICE].create({"partner_id": self.customer.id})

        with self.assertRaises(UserError):
            invoice.action_post()

    def test_a_negative_advance_or_final_invoice_is_not_posted(self):
        invoice = self.create_invoice(lines=((-100_000, 0),), kind="adjustment", post=False, adjusts_id=self.create_invoice().id)
        invoice.write({"kind": "final", "adjusts_id": False})

        with self.assertRaises(UserError):
            invoice.action_post()

    def test_only_a_draft_is_cancelled_or_deleted(self):
        draft = self.create_invoice(post=False)
        posted = self.create_invoice()

        draft.action_cancel()
        self.assertEqual(draft.status, "cancelled")
        with self.assertRaises(UserError):
            posted.action_cancel()
        with self.assertRaises(UserError):
            posted.unlink()
        self.create_invoice(post=False).unlink()
        self.assertTrue(posted.exists())
