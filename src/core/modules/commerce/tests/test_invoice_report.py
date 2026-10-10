import re

from odoo.tests import tagged

from .invoicing_case import InvoicingCase
from odoo.addons.commerce.constants.xml_ids import REPORT_INVOICE


@tagged("post_install", "-at_install")
class TestInvoiceReport(InvoicingCase):
    def test_the_invoice_report_shows_number_customer_and_amounts(self):
        invoice = self.create_invoice(lines=((5_000_000, 10),))
        report = self.env["ir.actions.report"]

        html = report._render_qweb_html(REPORT_INVOICE, invoice.ids)[0].decode()
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))

        for expected in (invoice.code, self.customer.name, "5,000,000", "500,000", "5,500,000", "Amount owed", "VAT 10 %"):
            with self.subTest(text=expected):
                self.assertIn(expected, text)

    def test_the_invoice_report_renders_as_pdf(self):
        invoice = self.create_invoice()

        content, _report_type = self.env["ir.actions.report"]._render_qweb_pdf(REPORT_INVOICE, invoice.ids)

        self.assertTrue(content)

    def test_print_opens_the_report(self):
        invoice = self.create_invoice()

        action = invoice.action_print()

        self.assertEqual((action["type"], action["report_name"]), ("ir.actions.report", "commerce.report_invoice"))
