from odoo import fields
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from .invoicing_case import InvoicingCase


@tagged("post_install", "-at_install")
class TestInvoiceImmutability(InvoicingCase):
    def test_a_posted_invoice_refuses_changes(self):
        invoice = self.create_invoice()
        other = self.env["res.partner"].create({"name": "Nhà máy Nước Bình An"})

        for vals in ({"partner_id": other.id}, {"due_date": "2030-01-01"}, {"kind": "advance"}):
            with self.subTest(vals=vals), self.assertRaises(UserError):
                invoice.write(vals)

    def test_the_lines_of_a_posted_invoice_are_frozen(self):
        invoice = self.create_invoice()
        line = invoice.line_ids

        refused = (
            lambda: line.write({"amount_untaxed": 1}),
            line.unlink,
            lambda: invoice.write(
                {"line_ids": [Command.create({"description": "More", "amount_untaxed": 1, "tax_rate": 0})]}
            ),
            lambda: self.env[line._name].create(
                {"invoice_id": invoice.id, "description": "More", "amount_untaxed": 1, "tax_rate": 0}
            ),
        )
        for action in refused:
            with self.subTest(action=action), self.assertRaises(UserError):
                action()

    def test_a_cancelled_invoice_is_frozen_too(self):
        invoice = self.create_invoice(post=False)
        invoice.action_cancel()

        with self.assertRaises(UserError):
            invoice.write({"due_date": "2030-01-01"})

    def test_a_draft_invoice_is_editable(self):
        invoice = self.create_invoice(post=False)

        invoice.write(
            {
                "due_date": "2030-01-01",
                "line_ids": [Command.create({"description": "More", "amount_untaxed": 1000, "tax_rate": 8})],
            }
        )

        self.assertEqual(len(invoice.line_ids), 2)

    def test_sending_fields_stay_writable_after_posting(self):
        invoice = self.create_invoice()

        invoice.write({"sent_at": fields.Datetime.now()})

        self.assertTrue(invoice.sent_at)
