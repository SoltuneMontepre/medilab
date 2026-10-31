from odoo.tests import tagged

from .order_case import OrderCase


@tagged("post_install", "-at_install")
class TestOrderTotals(OrderCase):
    def labels(self, order, lang):
        order = order.with_context(lang=lang)
        return [line["label"] for group in order.extra_total_fields for line in group["lines"]]

    def test_the_discount_total_is_labelled_in_the_user_language(self):
        self.env["res.lang"]._activate_lang("vi_VN")
        order = self.make_order([(self.lead_product, 2)])
        order._catalog_lines().discount = 10

        self.assertEqual(self.labels(order, "vi_VN"), ["Tổng ưu đãi"])
        self.assertEqual(self.labels(order, "en_US"), ["Total Advantage"])

    def test_an_order_without_a_discount_has_no_discount_total(self):
        order = self.make_order([(self.lead_product, 2)])

        self.assertEqual(self.labels(order, "en_US"), [])
