from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDemoInvoiceSeed(TransactionCase):
    def test_the_invoice_demo_can_be_loaded_twice(self):
        moves = self.env["account.move"]
        moves._seed_notification_demo()
        moves._seed_notification_demo()

        invoice = self.env.ref("sol_demo.demo_invoice_two_rates")
        advance = self.env.ref("sol_demo.demo_invoice_payos_advance")
        payment = self.env.ref("sol_demo.demo_payment_payos_advance")
        failed = self.env.ref("sol_demo.demo_push_failed")

        self.assertEqual(len(invoice.invoice_line_ids), 2)
        self.assertEqual(invoice.amount_untaxed, 3_000_000)
        self.assertEqual(invoice.amount_tax, 280_000)
        self.assertEqual(invoice.amount_total, 3_280_000)
        self.assertEqual(invoice.amount_residual, 3_280_000)
        self.assertEqual(advance.invoice_kind, "advance")
        self.assertTrue(advance.payment_state in ("paid", "in_payment", "partial"))
        self.assertTrue(payment.name and payment.name != "/")
        self.assertEqual(self.env.ref("sol_demo.demo_transaction_payos_advance").state, "done")
        self.assertEqual(failed.status, "failed")
        self.assertTrue(failed.error)
