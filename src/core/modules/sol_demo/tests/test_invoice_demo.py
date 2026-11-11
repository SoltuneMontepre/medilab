from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.services.model_lookup import reference_as


@tagged("post_install", "-at_install")
class TestDemoInvoiceSeed(TransactionCase):
    def test_the_invoice_demo_can_be_loaded_twice(self):
        moves = self.env["account.move"]
        moves._seed_notification_demo()
        moves._seed_notification_demo()

        invoice = self.env.ref("sol_demo.demo_account_move_two_rates")
        advance = self.env.ref("sol_demo.demo_account_move_payos_advance")
        payment = self.env.ref("sol_demo.demo_account_payment_payos_advance")
        failed = self.env.ref("sol_demo.demo_push_delivery_failed")

        self.assertEqual(len(invoice.invoice_line_ids), 2)
        self.assertEqual(invoice.amount_untaxed, 3_000_000)
        self.assertEqual(invoice.amount_tax, 280_000)
        self.assertEqual(invoice.amount_total, 3_280_000)
        self.assertEqual(invoice.amount_residual, 3_280_000)
        self.assertEqual(advance.invoice_kind, "advance")
        self.assertTrue(advance.payment_state in ("paid", "in_payment", "partial"))
        self.assertTrue(payment.name and payment.name != "/")
        self.assertEqual(self.env.ref("sol_demo.demo_payment_transaction_payos_advance").state, "done")
        self.assertEqual(failed.status, "failed")
        self.assertTrue(failed.error)

    def test_the_payment_demo_adds_the_journals_the_chart_lacks(self):
        # Odoo's generic chart, which a company outside Vietnam gets when account is installed, has no cash journal.
        journals = self.env["account.journal"]
        journals.search([("type", "in", ("cash", "bank")), ("company_id", "=", self.env.company.id)]).action_archive()
        moves = self.env["account.move"]
        product = self.env["product.product"].create(
            {"name": "Lead in water", "type": "service", "list_price": 5_000_000, "invoice_policy": "order"}
        )
        order = moves._demo_order(self.env.ref("sol_demo.demo_res_partner_an_phu"), product, self.env["account.tax"])
        advance = order.create_advance_invoice(amount=2_500_000)
        final = order.create_final_invoice()
        final.action_post()

        cash, transfer, pending, rejected = moves._demo_payments(advance, final)

        cash_journal = reference_as(self.env["account.journal"], "sol_demo.demo_account_journal_cash")
        bank_journal = reference_as(self.env["account.journal"], "sol_demo.demo_account_journal_bank")
        self.assertEqual((cash | rejected).journal_id, cash_journal)
        self.assertEqual((transfer | pending).journal_id, bank_journal)
        self.assertEqual(cash_journal.type, "cash")
        self.assertEqual(bank_journal.type, "bank")
        self.assertEqual(cash_journal.with_context(lang="vi_VN").name, "Tiền mặt")
        self.assertEqual(bank_journal.with_context(lang="vi_VN").name, "Ngân hàng")
        self.assertNotEqual(cash.state, "draft")
        self.assertEqual(rejected.state, "canceled")
