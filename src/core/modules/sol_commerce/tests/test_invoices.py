from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import HttpCase, tagged

from .invoicing_case import InvoicingCase


@tagged("post_install", "-at_install")
class TestInvoices(InvoicingCase):
    def test_an_advance_and_a_final_invoice_bill_the_order_once(self):
        advance = self.order.create_advance_invoice(amount=1_000_000)
        final = self.order.create_final_invoice()
        final.action_post()

        self.assertEqual(advance.invoice_kind, "advance")
        self.assertEqual(advance.state, "posted")
        self.assertEqual(advance.amount_total, 1_000_000)
        self.assertEqual(advance.order_id, self.order)
        self.assertIn(str(advance.invoice_date.year), advance.name)
        self.assertEqual(final.invoice_kind, "final")
        self.assertEqual(final.amount_total, self.order.amount_total - advance.amount_total)

    def test_sending_a_quotation_is_the_hook_that_posts_the_advance(self):
        invoice = self.order._on_quotation_sent(percentage=20)

        self.assertEqual(len(invoice), 1)
        self.assertEqual((invoice.invoice_kind, invoice.state, invoice.amount_total), ("advance", "posted", 1_000_000))

    def test_a_lowering_adjustment_reduces_what_is_owed_and_leaves_the_invoice(self):
        invoice = self.order.create_advance_invoice()
        self.assertEqual(invoice.amount_total, 5_000_000)

        credit = invoice.action_adjust(-500_000)

        self.assertEqual(invoice.amount_total, 5_000_000)
        self.assertEqual(credit.move_type, "out_refund")
        self.assertEqual(credit.invoice_kind, "adjustment")
        self.assertEqual(credit.reversed_entry_id, invoice)
        self.assertEqual(credit.amount_total, 500_000)
        self.assertEqual(invoice.amount_owed, 4_500_000)

    def test_a_raising_adjustment_adds_what_is_owed(self):
        invoice = self.order.create_advance_invoice()

        raised = invoice.action_adjust(500_000)

        self.assertEqual(raised.move_type, "out_invoice")
        self.assertEqual(raised.adjusted_invoice_id, invoice)
        self.assertEqual(invoice.amount_total, 5_000_000)
        self.assertEqual(invoice.amount_owed, 5_500_000)

    def test_a_posted_invoice_cannot_go_back_to_draft(self):
        invoice = self.order.create_advance_invoice()

        with self.assertRaises(UserError):
            invoice.button_draft()
        self.assertEqual(invoice.state, "posted")

    def test_posting_and_adjusting_need_the_accountant(self):
        invoice = self.order.create_advance_invoice()
        clerk = self.env["res.users"].create(
            {
                "name": "Clerk",
                "login": "invoice.clerk",
                "group_ids": [Command.set(self.env.ref("base.group_user").ids)],
            }
        )

        with self.assertRaises(AccessError):
            invoice.with_user(clerk).action_adjust(-1)
        with self.assertRaises(AccessError):
            invoice.with_user(clerk).action_print_invoice()

    def test_the_pdf_names_the_invoice_kind(self):
        invoice = self.order.create_advance_invoice()

        html = self.env["ir.actions.report"]._render_qweb_html("account.account_invoices", invoice.ids)[0]

        self.assertIn(b"medilab_invoice_kind", html)
        self.assertIn(b"Advance", html)

    def test_a_customer_reads_only_their_posted_invoices(self):
        invoice = self.order.create_advance_invoice()
        draft = self.order.create_final_invoice()
        other_partner = self.env["res.partner"].create({"name": "Other customer"})
        customer = self.portal_user("khach.a", self.partner)
        other = self.portal_user("khach.b", other_partner)

        self.assertEqual(invoice.with_user(customer).amount_total, 5_000_000)
        with self.assertRaises(AccessError):
            invoice.with_user(other).read(["amount_total"])
        with self.assertRaises(AccessError):
            draft.with_user(customer).read(["amount_total"])


@tagged("post_install", "-at_install")
class TestInvoicePortalUrl(InvoicingCase, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoice = cls.order.create_advance_invoice()
        other_partner = cls.env["res.partner"].create({"name": "Other customer"})
        cls.other = cls.portal_user("khach.url", other_partner)

    def test_another_customers_invoice_url_does_not_open(self):
        self.authenticate(self.other.login, self.other.login)
        response = self.url_open(f"/my/invoices/{self.invoice.id}", allow_redirects=False)

        self.assertIn(response.status_code, (301, 302, 303))
        self.assertTrue(response.headers["Location"].endswith("/my"))
