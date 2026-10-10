from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .invoicing_case import InvoicingCase
from odoo.addons.commerce.constants.models import MODEL_INVOICE


@tagged("post_install", "-at_install")
class TestInvoicePermissions(InvoicingCase):
    def test_a_person_without_permissions_sees_no_invoice(self):
        self.create_invoice()

        invoices = self.as_person(self.env[MODEL_INVOICE], self.chemist)

        with self.assertRaises(AccessError):
            invoices.search([])
        with self.assertRaises(AccessError):
            invoices.create({"partner_id": self.customer.id})

    def test_sales_reads_invoices_but_cannot_post_or_change_them(self):
        invoice = self.create_invoice(post=False)
        as_sales = self.as_person(invoice, self.salesperson)

        self.assertEqual(as_sales.read(["code"])[0]["id"], invoice.id)
        with self.assertRaises(AccessError):
            as_sales.action_post()
        with self.assertRaises(AccessError):
            as_sales.write({"due_date": "2030-01-01"})
        views = self.as_person(self.env[MODEL_INVOICE], self.salesperson).get_views([(False, "list"), (False, "form")])["views"]
        for view_type, view in views.items():
            root = etree.fromstring(view["arch"])
            with self.subTest(view=view_type):
                self.assertEqual([root.get(name) for name in ("create", "edit", "delete")], ["False"] * 3)

    def test_the_accountant_creates_posts_and_adjusts_invoices(self):
        invoices = self.as_person(self.env[MODEL_INVOICE], self.accountant)

        invoice = invoices.create({"partner_id": self.customer.id, "line_ids": [(0, 0, {"description": "Lead (Pb)", "amount_untaxed": 1_000_000, "tax_rate": 8})]})
        invoice.action_post()
        adjustment = invoices.browse(invoice.action_create_adjustment()["res_id"])

        self.assertEqual(invoice.status, "posted")
        self.assertEqual(adjustment.adjusts_id, invoice)
