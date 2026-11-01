from odoo.fields import Command
from odoo.tests import TransactionCase

from odoo.addons.sol_laboratory.services.record_id import persisted_ids


class TestVietnameseAccountingLocalization(TransactionCase):
    def test_vietnamese_chart_and_vat_invoice_are_compatible(self):
        company = self.env.company
        vietnam = self.env.ref("base.vn")
        self.assertEqual(company.chart_template, "vn")
        self.assertEqual(company.account_fiscal_country_id, vietnam)
        self.assertEqual(company.currency_id.name, "VND")

        tax = self.env["account.tax"].search(
            [
                ("company_id", "=", company.id),
                ("country_id", "=", vietnam.id),
                ("type_tax_use", "=", "sale"),
                ("amount_type", "=", "percent"),
                ("amount", "=", 10),
            ],
            limit=1,
        )
        self.assertTrue(tax)
        self.assertEqual(
            len(tax.invoice_repartition_line_ids.filtered(lambda line: line.repartition_type == "base")),
            1,
        )
        self.assertEqual(
            len(tax.refund_repartition_line_ids.filtered(lambda line: line.repartition_type == "base")),
            1,
        )

        income_account = self.env["account.account"].search(
            [
                ("company_ids", "in", company.id),
                ("account_type", "=", "income"),
            ],
            limit=1,
        )
        partner = self.env["res.partner"].create({"name": "Vietnam VAT test"})
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": partner.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "VAT test line",
                            "quantity": 1,
                            "price_unit": 100_000,
                            "account_id": income_account.id,
                            "tax_ids": [Command.set(persisted_ids(tax))],
                        }
                    )
                ],
            }
        )
        invoice.action_post()
        self.assertEqual(invoice.state, "posted")
        self.assertFalse(invoice.fiscal_position_id)
        self.assertEqual(invoice.invoice_line_ids.tax_ids, tax)
