from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_commerce.constants.notifications import EVENT_QUOTATION_SENT
from odoo.addons.sol_laboratory.tests.assertions import assert_instance


@tagged("post_install", "-at_install")
class TestDemoQuotationLanguage(TransactionCase):
    def test_sent_quotations_note_the_advance_invoice_in_the_salesperson_language(self):
        sales = self.env.ref("sol_demo.demo_res_users_sales")
        order = self.env.ref("sol_demo.demo_sale_order_quotation_sent")
        notes = order.message_ids.filtered(lambda message: message.subtype_id.code != EVENT_QUOTATION_SENT)
        bodies = notes.mapped("body")

        self.assertEqual(sales.lang, "vi_VN")
        self.assertTrue(any("Hoá đơn khoản trả trước" in (body or "") for body in bodies), bodies)

    def test_the_customer_notice_is_in_the_contact_language(self):
        order = self.env.ref("sol_demo.demo_sale_order_quotation_sent")
        notice = order.message_ids.filtered(lambda message: message.subtype_id.code == EVENT_QUOTATION_SENT)
        expected = "đã sẵn sàng" if order.partner_id.lang == "vi_VN" else "is ready"

        self.assertIn(expected, assert_instance(notice.body, str))
