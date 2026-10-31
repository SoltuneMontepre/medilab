from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.notifications import EVENT_QUOTATION_SENT


@tagged("post_install", "-at_install")
class TestQuotationLanguage(OrderCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("vi_VN")

    def send(self, customer_lang, user, order=None):
        """Send the quotation as the user does, in the user's interface language."""
        self.contact.lang = customer_lang
        order = order or self.make_quotable_order()
        order.with_user(user).with_context(lang=user.lang).action_send_quotation()
        return order

    def notice(self, order):
        return order.message_ids.filtered(lambda message: message.subtype_id.code == EVENT_QUOTATION_SENT)

    def test_the_customer_reads_the_quotation_notice_in_their_language(self):
        self.sales.lang = "en_US"
        order = self.send("vi_VN", self.sales)

        notice = self.notice(order)
        self.assertIn("đã sẵn sàng", notice.body)
        self.assertNotIn("is ready", notice.body)

    def test_an_english_customer_reads_it_in_english_when_sales_works_in_vietnamese(self):
        self.sales.lang = "vi_VN"
        order = self.send("en_US", self.sales)

        self.assertIn("is ready", self.notice(order).body)

    def test_the_notice_without_an_advance_follows_the_customer_language(self):
        order = self.make_quotable_order()
        order.advance_method = "none"
        self.head.lang = "en_US"
        self.send("vi_VN", self.head, order)

        self.assertIn("Hãy chấp nhận trước", self.notice(order).body)

    def test_the_internal_down_payment_note_stays_in_the_salesperson_language(self):
        self.sales.lang = "vi_VN"
        order = self.send("en_US", self.sales)

        bodies = (order.message_ids - self.notice(order)).mapped("body")
        self.assertTrue(any("Hoá đơn khoản trả trước" in body for body in bodies), bodies)
        self.assertIn("is ready", self.notice(order).body)
