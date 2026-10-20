from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import HttpCase, new_test_user, tagged

from .invoicing_case import InvoicingCase
from odoo.addons.sol_laboratory.tests.audit_case import AuditLookup

# The password of the test accountant is its login.
ACCOUNTANT = "ketoan.audit"


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
        self.assertEqual(credit.amount_residual, 0)
        self.assertEqual(invoice.amount_residual, 4_500_000)
        self.assertEqual(invoice.amount_owed, 4_500_000)

        payment = self.env["account.payment"].create_pending_payment(invoice, 4_500_000, "cash")
        payment.action_post()
        self.assertEqual(invoice.amount_residual, 0)
        self.assertEqual(invoice.amount_owed, 0)

    def test_an_adjustment_uses_the_tax_of_the_invoice_line(self):
        tax = self.env["account.tax"].create(
            {
                "name": "Adjustment VAT 10",
                "amount": 10,
                "amount_type": "percent",
                "type_tax_use": "sale",
                "price_include_override": "tax_excluded",
            }
        )
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_kind": "final",
                "partner_id": self.partner.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "quantity": 1,
                            "price_unit": 1_000_000,
                            "tax_ids": [Command.set(tax.ids)],
                        }
                    )
                ],
            }
        )
        invoice.action_post()

        credit = invoice.action_adjust(-100_000)

        self.assertEqual(credit.invoice_line_ids.tax_ids, tax)
        self.assertEqual(credit.amount_untaxed, 100_000)
        self.assertEqual(credit.amount_tax, 10_000)
        self.assertEqual(credit.amount_total, 110_000)
        self.assertEqual(invoice.amount_residual, invoice.amount_total - 110_000)
        self.assertEqual(invoice.amount_owed, invoice.amount_residual)

    def test_a_raising_adjustment_adds_what_is_owed(self):
        invoice = self.order.create_advance_invoice()

        raised = invoice.action_adjust(500_000)

        self.assertEqual(raised.move_type, "out_invoice")
        self.assertEqual(raised.adjusted_invoice_id, invoice)
        self.assertEqual(invoice.amount_total, 5_000_000)
        self.assertEqual(invoice.amount_owed, 5_500_000)
        self.assertEqual(invoice.amount_residual, 5_000_000)
        self.assertEqual(raised.amount_residual, 500_000)

    def test_repeated_adjustments_change_the_obligation_once_each(self):
        invoice = self.order.create_advance_invoice()

        invoice.action_adjust(-500_000)
        invoice.action_adjust(-500_000)
        raised = invoice.action_adjust(500_000)

        self.assertEqual(invoice.amount_total, 5_000_000)
        self.assertEqual(invoice.amount_residual, 4_000_000)
        self.assertEqual(invoice.amount_owed, 4_500_000)
        self.assertEqual(raised.amount_residual, 500_000)
        payment = self.env["account.payment"].create_pending_payment(invoice, 4_000_000, "cash")
        payment.action_post()
        self.assertEqual(invoice.amount_residual, 0)
        self.assertEqual(invoice.amount_owed, 500_000)

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

    def test_two_tax_rates_are_added_on_the_invoice_and_its_pdf(self):
        vat8 = self.env["account.tax"].create(
            {
                "name": "VAT 8%",
                "amount": 8,
                "amount_type": "percent",
                "type_tax_use": "sale",
                "price_include_override": "tax_excluded",
            }
        )
        vat10 = self.env["account.tax"].create(
            {
                "name": "VAT 10%",
                "amount": 10,
                "amount_type": "percent",
                "type_tax_use": "sale",
                "price_include_override": "tax_excluded",
            }
        )
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_kind": "final",
                "partner_id": self.partner.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "quantity": 1,
                            "price_unit": 1_000_000,
                            "tax_ids": [Command.set(vat8.ids)],
                        }
                    ),
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "quantity": 1,
                            "price_unit": 2_000_000,
                            "tax_ids": [Command.set(vat10.ids)],
                        }
                    ),
                ],
            }
        )
        invoice.action_post()
        html = self.env["ir.actions.report"]._render_qweb_html("account.account_invoices", invoice.ids)[0]

        self.assertEqual(invoice.amount_untaxed, 3_000_000)
        self.assertEqual(invoice.amount_tax, 280_000)
        self.assertEqual(invoice.amount_total, 3_280_000)
        self.assertEqual(invoice.amount_residual, 3_280_000)
        self.assertIn(b"VAT 8%", html)
        self.assertIn(b"VAT 10%", html)

    def test_the_pdf_names_the_invoice_kind(self):
        invoice = self.order.create_advance_invoice()

        html = self.env["ir.actions.report"]._render_qweb_html("account.account_invoices", invoice.ids)[0]

        self.assertIn(b"medilab_laboratory_header", html)
        self.assertIn(self.env.company.name.encode(), html)
        self.assertIn(invoice.name.encode(), html)
        self.assertIn(self.partner.name.encode(), html)
        self.assertIn(b"medilab_invoice_kind", html)
        self.assertIn(b"Advance", html)
        self.assertIn(b"medilab_subtotal", html)
        self.assertIn(b"medilab_grand_total", html)
        self.assertIn(b"medilab_paid_amount", html)
        self.assertIn(b"medilab_amount_owed", html)
        self.assertIn(b"medilab_payment_details", html)

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
class TestInvoicePortalUrl(AuditLookup, InvoicingCase, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoice = cls.order.create_advance_invoice()
        other_partner = cls.env["res.partner"].create({"name": "Other customer"})
        cls.customer = cls.portal_user("khach.owner", cls.partner)
        cls.other = cls.portal_user("khach.url", other_partner)
        cls.accountant = new_test_user(
            cls.env, login=ACCOUNTANT, password=ACCOUNTANT, groups="base.group_user,account.group_account_manager"
        )

    def test_another_customers_invoice_url_does_not_open(self):
        self.authenticate(self.other.login, self.other.login)
        response = self.url_open(f"/my/invoices/{self.invoice.id}", allow_redirects=False)

        self.assertIn(response.status_code, (301, 302, 303))
        self.assertTrue(response.headers["Location"].endswith("/my"))

    def test_a_draft_invoice_url_does_not_open(self):
        draft = self.order.create_final_invoice()
        customer = self.portal_user("khach.draft", self.partner)
        self.authenticate(customer.login, customer.login)

        response = self.url_open(f"/my/invoices/{draft.id}", allow_redirects=False)

        self.assertIn(response.status_code, (301, 302, 303))
        self.assertTrue(response.headers["Location"].endswith("/my"))

    def test_the_owner_opens_the_invoice_and_its_pdf(self):
        self.authenticate(self.customer.login, self.customer.login)

        page = self.url_open(f"/my/invoices/{self.invoice.id}")
        pdf = self.url_open(f"/my/invoices/{self.invoice.id}?report_type=pdf&download=true")
        self.authenticate(self.other.login, self.other.login)
        hidden = self.url_open(f"/my/invoices/{self.invoice.id}?report_type=pdf&download=true", allow_redirects=False)

        self.assertEqual(page.status_code, 200)
        self.assertIn(self.invoice.name, page.text)
        self.assertEqual(pdf.status_code, 200)
        self.assertIn("pdf", pdf.headers.get("Content-Type", "").lower())
        self.assertIn(hidden.status_code, (301, 302, 303))
        self.assertTrue(hidden.headers["Location"].endswith("/my"))
        self.assertEqual(self.entries(self.invoice, "download").user_id, self.customer)

    def test_downloading_an_invoices_documents_in_the_back_office_is_a_download(self):
        self.authenticate(self.accountant.login, self.accountant.login)

        self.url_open(f"/account/download_invoice_documents/{self.invoice.id}/pdf")

        self.assertEqual(self.entries(self.invoice, "download").user_id, self.accountant)

    def test_printing_an_invoice_in_the_back_office_is_a_download(self):
        report = self.env.ref("account.account_invoices")
        self.authenticate(self.accountant.login, self.accountant.login)

        self.url_open(f"/report/pdf/{report.report_name}/{self.invoice.id}")

        entry = self.entries(self.invoice, "download")
        self.assertEqual((entry.note, entry.user_id), (report.name, self.accountant))
        self.assertFalse(entry.change_ids)

    def test_a_token_opens_only_that_posted_invoice(self):
        self.opener.cookies.clear()
        self.invoice._portal_ensure_token()
        draft = self.order.create_final_invoice()
        draft._portal_ensure_token()

        opened = self.url_open(f"/my/invoices/{self.invoice.id}?access_token={self.invoice.access_token}")
        wrong = self.url_open(f"/my/invoices/{self.invoice.id}?access_token=not-the-token", allow_redirects=False)
        hidden = self.url_open(f"/my/invoices/{draft.id}?access_token={draft.access_token}", allow_redirects=False)

        self.assertEqual(opened.status_code, 200)
        self.assertIn(hidden.status_code, (301, 302, 303))
        self.assertTrue(hidden.headers["Location"].endswith("/my"))
        self.assertIn(wrong.status_code, (301, 302, 303))
        self.assertTrue(wrong.headers["Location"].endswith("/my"))
