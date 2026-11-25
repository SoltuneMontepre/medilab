from odoo.tests import HttpCase, tagged

from .invoicing_case import InvoicingCase, post_legacy_advance_invoice

VIETNAMESE_WORDS = "Năm triệu đồng"
ENGLISH_WORDS = "Five Million Dong"


@tagged("post_install", "-at_install")
class TestInvoiceAmountInWords(InvoicingCase, HttpCase):
    """The invoice of 5,000,000 VND shows its amount in words in the customer's language."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.display_invoice_amount_total_words = True
        cls.invoice = post_legacy_advance_invoice(cls.order)
        cls.customer = cls.portal_user("khach.words", cls.partner)

    def test_a_vietnamese_customer_reads_the_invoice_on_the_portal(self):
        self.partner.lang = "vi_VN"
        self.authenticate(self.customer.login, self.customer.login)

        page = self.url_open(f"/my/invoices/{self.invoice.id}?report_type=html")

        self.assertEqual(page.status_code, 200)
        self.assertIn(VIETNAMESE_WORDS, page.content.decode())

    def test_the_printed_and_emailed_invoice_read_the_amount_in_vietnamese(self):
        self.partner.write({"lang": "vi_VN", "email": "an@example.com"})

        html = self.env["ir.actions.report"]._render_qweb_html("account.account_invoices", self.invoice.ids)[0]
        message = self.invoice.action_send_invoice()

        self.assertIn(VIETNAMESE_WORDS, html.decode())
        self.assertIn(VIETNAMESE_WORDS, message.attachment_ids.raw.decode())

    def test_an_english_customer_keeps_the_english_wording(self):
        self.partner.lang = "en_US"

        html = self.env["ir.actions.report"]._render_qweb_html("account.account_invoices", self.invoice.ids)[0]

        self.assertIn(ENGLISH_WORDS, html.decode())
