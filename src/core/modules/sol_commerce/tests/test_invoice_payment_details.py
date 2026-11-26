from odoo.tests import HttpCase, tagged

from .invoicing_case import InvoicingCase, post_legacy_advance_invoice

BANK_NAME = "Vietcombank"
ACCOUNT_NUMBER = "0071000123456"


@tagged("post_install", "-at_install")
class TestInvoicePaymentDetails(InvoicingCase, HttpCase):
    """An unpaid invoice of a laboratory whose bank account is set up for VietQR."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        company.qr_code = True
        company.partner_id.city = "Ho Chi Minh"
        # Posting drops a bank account that is not trusted from the invoice, and the QR code with it.
        cls.env["res.partner.bank"].create(
            {
                "partner_id": company.partner_id.id,
                "account_number": ACCOUNT_NUMBER,
                "bank_name": BANK_NAME,
                "bank_bic": "970436",
                "proxy_type": "bank_acc",
                "proxy_value": ACCOUNT_NUMBER,
                "allow_out_payment": True,
            }
        )
        cls.invoice = post_legacy_advance_invoice(cls.order)
        cls.customer = cls.portal_user("khach.bank", cls.partner)

    def assert_payment_details(self, document: str):
        account = document.partition('class="medilab_payment_account"')[2].partition("</div>")[0]
        qr_code = document.partition('id="qrcode_image"')[2].partition("</div>")[0]

        self.assertIn(BANK_NAME, account)
        self.assertIn(ACCOUNT_NUMBER, account)
        self.assertIn('src="data:image/png;base64,', qr_code)
        self.assertEqual(self.invoice.qr_code_method, "emv_qr")

    def test_the_printed_invoice_shows_the_bank_account_and_the_vietqr_code(self):
        printed = self.env["ir.actions.report"]._render_qweb_html("account.account_invoices", self.invoice.ids)[0]

        self.assert_payment_details(printed.decode())

    def test_the_portal_invoice_shows_the_bank_account_and_the_vietqr_code(self):
        self.authenticate(self.customer.login, self.customer.login)
        address = f"/my/invoices/{self.invoice.id}"

        page = self.url_open(address)
        shown = self.url_open(f"{address}?report_type=html")
        pdf = self.url_open(f"{address}?report_type=pdf&download=true")

        self.assertEqual(page.status_code, 200)
        self.assertIn("report_type=html", page.text)
        self.assertEqual(shown.status_code, 200)
        self.assert_payment_details(shown.text)
        self.assertEqual(pdf.status_code, 200)
        self.assertIn("pdf", pdf.headers.get("Content-Type", "").lower())
