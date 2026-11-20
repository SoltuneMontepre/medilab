from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_commerce.constants.notifications import EVENT_QUOTATION_SENT
from odoo.addons.sol_laboratory.tests.assertions import assert_instance


@tagged("post_install", "-at_install")
class TestDemoQuotationLanguage(TransactionCase):
    def test_the_sent_demo_quotation_requests_an_advance_without_posting_an_invoice(self):
        order = self.env.ref("sol_demo.demo_sale_order_quotation_sent")
        request = order.payment_request_id

        self.assertEqual(request.quotation_id, order._latest_quotation())
        self.assertEqual((request.kind, request.state), ("advance", "open"))
        self.assertGreater(request.amount, 0)
        self.assertFalse(order.invoice_ids)

    def test_the_customer_notice_is_in_the_contact_language(self):
        order = self.env.ref("sol_demo.demo_sale_order_quotation_sent")
        notice = order.message_ids.filtered(lambda message: message.subtype_id.code == EVENT_QUOTATION_SENT)
        expected = "Hãy thanh toán tạm ứng" if order.partner_id.lang == "vi_VN" else "Pay the advance of"

        self.assertIn(expected, assert_instance(notice.body, str))
