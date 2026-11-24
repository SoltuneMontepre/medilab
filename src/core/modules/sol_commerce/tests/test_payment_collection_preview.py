from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_PAYMENT_COLLECTION


@tagged("post_install", "-at_install")
class TestPaymentCollectionPreview(OrderCase):
    """Sales records a payment at the counter beside a summary of what is due and, for a bank transfer, the details
    the customer transfers to."""

    def collection(self, order, method):
        return (
            self.env[MODEL_PAYMENT_COLLECTION]
            .with_user(self.sales)
            .create({"order_id": order.id, "method": method, "amount": 1000})
        )

    def sent_order(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        return order

    def test_the_summary_shows_the_quotation_the_request_and_what_remains(self):
        order = self.sent_order()

        summary = str(self.collection(order, "cash").summary_html)

        self.assertIn(order._latest_quotation().code, summary)
        self.assertIn(order.currency_id.format(order.amount_total), summary)
        self.assertIn(order.currency_id.format(order.payment_request_id.remaining_amount), summary)

    def test_a_cash_payment_shows_no_transfer_details(self):
        self.assertFalse(self.collection(self.sent_order(), "cash").qr_html)

    def test_a_bank_transfer_shows_the_company_account(self):
        order = self.sent_order()
        self.env["res.partner.bank"].create(
            {
                "partner_id": order.company_id.partner_id.id,
                "account_number": "0071000123456",
                "holder_name": "MEDILAB LABORATORY",
                "bank_name": "Vietcombank",
            }
        )

        details = str(self.collection(order, "bank_transfer").qr_html)

        for value in ("0071000123456", "MEDILAB LABORATORY", "Vietcombank", order._latest_quotation().code):
            with self.subTest(value=value):
                self.assertIn(value, details)

    def test_a_bank_transfer_without_an_account_says_so(self):
        order = self.sent_order()
        order.company_id.partner_id.bank_ids.unlink()

        details = str(self.collection(order, "bank_transfer").qr_html)

        self.assertIn("not configured", details)
