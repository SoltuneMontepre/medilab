from odoo.exceptions import UserError
from odoo.tests import tagged

from .payos_case import CREATE_PATH, PayosCase, link_data, signed_answer
from odoo.addons.commerce.constants.payos import JOB_CALLS

RECEIPT_FORMAT = r"^\d{4} \d{2}/PT$"
CANCEL_PATH = ("POST", "/v2/payment-requests/")


@tagged("post_install", "-at_install")
class TestPaymentRecording(PayosCase):
    def test_the_accountant_records_a_confirmed_payment_with_its_receipt(self):
        invoice = self.create_invoice(lines=((5_000_000, 0),))

        payment = self.pay(invoice, 2_000_000)

        self.assertEqual(
            (payment.status, payment.recorded_by_id, payment.reviewed_by_id),
            ("confirmed", self.accountant.user_id, self.accountant.user_id),
        )
        self.assertRegex(payment.receipt_code, RECEIPT_FORMAT)
        self.assertTrue(payment.receipt_attachment_id.raw)
        self.assertEqual((invoice.amount_paid, invoice.amount_pending, invoice.amount_owed), (2_000_000, 0, 3_000_000))
        self.assertEqual(invoice.payment_status, "partially_paid")

    def test_sales_records_a_pending_payment_that_does_not_count_yet(self):
        invoice = self.create_invoice(lines=((5_000_000, 0),))

        payment = self.pay(invoice, 2_000_000, user=self.salesperson)

        self.assertEqual(
            (payment.status, payment.recorded_by_id, payment.receipt_code), ("pending", self.salesperson.user_id, False)
        )
        self.assertEqual((invoice.amount_paid, invoice.amount_pending, invoice.amount_owed), (0, 2_000_000, 5_000_000))
        self.assertEqual(invoice.payment_status, "not_paid")

    def test_partial_payments_pay_the_invoice_in_instalments(self):
        invoice = self.create_invoice(lines=((5_000_000, 0),))

        self.pay(invoice, 2_000_000)
        self.pay(invoice, 3_000_000, method="bank_transfer")

        self.assertEqual((invoice.amount_paid, invoice.amount_owed, invoice.payment_status), (5_000_000, 0, "paid"))
        self.assertFalse(invoice.is_overpaid)

    def test_a_manual_payment_above_the_owed_amount_is_refused(self):
        invoice = self.create_invoice(lines=((5_000_000, 0),))
        self.pay(invoice, 4_000_000)

        for user in (self.accountant, self.salesperson):
            with self.subTest(user=user.name), self.assertRaisesRegex(UserError, "exceeds"):
                self.pay(invoice, 1_000_001, user=user)
        self.assertEqual(invoice.amount_owed, 1_000_000)

    def test_a_payment_goes_on_a_posted_advance_or_final_invoice(self):
        draft = self.create_invoice(post=False)
        posted = self.create_invoice()
        adjustment = self.create_invoice(lines=((100_000, 8),), kind="adjustment", adjusts_id=posted.id)

        for invoice in (draft, adjustment):
            with self.subTest(invoice=invoice.kind), self.assertRaisesRegex(UserError, "posted advance or final"):
                self.pay(invoice, 100_000)

    def test_an_online_payment_is_never_recorded_by_hand(self):
        invoice = self.create_invoice()

        with self.assertRaisesRegex(UserError, "never by hand"):
            self.pay(invoice, 100_000, method="online")

    def test_register_payment_opens_the_form_on_the_invoice(self):
        invoice = self.create_invoice(lines=((5_000_000, 0),))

        action = invoice.with_user(self.salesperson.user_id).action_register_payment()

        self.assertEqual(action["context"], {"default_invoice_id": invoice.id, "default_amount": 5_000_000})

    def test_settling_the_invoice_by_hand_queues_the_cancellation_of_its_pending_links(self):
        invoice = self.create_invoice(lines=((5_000_000, 0),))
        link, fake = self.create_link(invoice)
        fake.answers = {}

        self.pay(invoice, 5_000_000)

        self.assertEqual(invoice.payment_status, "paid")
        self.assertEqual(link.status, "pending")
        item = self.job_items(JOB_CALLS, "pending")
        self.assertEqual(item.mapped("item_key"), [f"cancel:{link.id}"])
        self.assertEqual(fake.paths(), [CREATE_PATH])

        fake.answers[CANCEL_PATH] = lambda m, p, b: signed_answer(link_data(link, status="CANCELLED"))
        self.run_job(JOB_CALLS)

        self.assertEqual((link.status, item.status), ("cancelled", "done"))
