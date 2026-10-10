from odoo.tests import tagged

from .invoicing_case import InvoicingCase


@tagged("post_install", "-at_install")
class TestInvoiceAmounts(InvoicingCase):
    def test_net_tax_and_total_add_up_per_line_and_per_rate(self):
        invoice = self.create_invoice(lines=((1_234_567, 8), (2_000_000, 8), (1_000_000, 10)), post=False)

        self.assertEqual(invoice.line_ids.mapped("amount_tax"), [98_765, 160_000, 100_000])
        self.assertEqual(invoice.amount_untaxed, 4_234_567)
        self.assertEqual(invoice.amount_tax, 358_765)
        self.assertEqual(invoice.amount_total, 4_593_332)
        self.assertEqual(invoice.tax_totals_by_rate(), [(8.0, 3_234_567, 258_765), (10.0, 1_000_000, 100_000)])
        self.assertEqual(sum(tax for _rate, _net, tax in invoice.tax_totals_by_rate()), invoice.amount_tax)

    def test_an_advance_deduction_lowers_the_final_invoice(self):
        self.create_invoice(lines=((2_500_000, 8),), kind="advance")
        final = self.env["medilab.invoice"].create(
            {
                "partner_id": self.customer.id,
                "kind": "final",
                "line_ids": [
                    (0, 0, {"description": "Lead (Pb)", "amount_untaxed": 3_000_000, "tax_rate": 8}),
                    (0, 0, {"description": "Coliforms", "amount_untaxed": 2_000_000, "tax_rate": 8}),
                    (0, 0, {"description": "Advance deducted", "kind": "advance_deduction", "amount_untaxed": -2_500_000, "tax_rate": 8}),
                ],
            }
        )

        self.assertEqual((final.amount_untaxed, final.amount_tax, final.amount_total), (2_500_000, 200_000, 2_700_000))

    def test_amounts_are_in_vnd(self):
        invoice = self.create_invoice(post=False)

        self.assertEqual(invoice.currency_id, self.env.ref("base.VND"))
        self.assertEqual(invoice.line_ids.currency_id, self.env.ref("base.VND"))
