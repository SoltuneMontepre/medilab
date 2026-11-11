from odoo.tests import TransactionCase

from odoo.addons.sol_demo.demo_quotations import _sales_tax


class TestDemoQuotationTax(TransactionCase):
    def test_sales_tax_is_scoped_to_company_and_fiscal_country(self):
        vietnam = self.env.ref("base.vn")
        usa = self.env.ref("base.us")
        partner = self.env["res.partner"].create({"name": "Other company", "country_id": usa.id})
        other_company = self.env["res.company"].create({"name": "Other company", "partner_id": partner.id})
        group = self.env["account.tax.group"].create(
            {
                "name": "Other company VAT",
                "company_id": other_company.id,
                "country_id": usa.id,
            }
        )
        self.env["account.tax"].create(
            {
                "name": "Foreign 77% VAT",
                "amount": 77,
                "amount_type": "percent",
                "type_tax_use": "sale",
                "company_id": other_company.id,
                "country_id": usa.id,
                "tax_group_id": group.id,
            }
        )

        tax = _sales_tax(self.env, 77)

        self.assertEqual(tax.company_id, self.env.company)
        self.assertEqual(tax.country_id, vietnam)
