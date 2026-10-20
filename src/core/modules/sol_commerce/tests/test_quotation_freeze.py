from odoo.exceptions import UserError
from odoo.tests import tagged

from .order_case import OrderCase


@tagged("post_install", "-at_install")
class TestQuotationFreeze(OrderCase):
    """What the customer was quoted stays as it was until the quotation is revised."""

    def test_a_line_price_and_a_sample_name_are_refused_on_a_sent_quotation(self):
        order = self.sent_order()
        line = order._catalog_lines()
        sample = order.sample_ids
        total = order._latest_quotation().amount_total

        for user in (self.env.user, self.sales):
            with self.subTest(user=user.login):
                with self.assertRaises(UserError):
                    line.with_user(user).write({"price_unit": 1})
                with self.assertRaises(UserError):
                    sample.with_user(user).write({"customer_sample_name": "Another sample"})
        with self.assertRaises(UserError):
            line.unlink()
        with self.assertRaises(UserError):
            sample.unlink()
        with self.assertRaises(UserError):
            self.make_sample(order)
        with self.assertRaises(UserError):
            self.env["sale.order.line"].create(
                {"order_id": order.id, "product_id": self.lead_product.product_variant_ids.id}
            )

        self.assertEqual(order.amount_total, total)
        self.assertEqual(sample.customer_sample_name, "Lavie bottled water 1 L")

    def test_an_accepted_quotation_keeps_its_lines_and_samples(self):
        order = self.sent_order()
        self.pay_advance(order)
        self.assertEqual(order._latest_quotation().status, "accepted")

        with self.assertRaises(UserError):
            order._catalog_lines().write({"product_uom_qty": 4})
        with self.assertRaises(UserError):
            order.sample_ids.write({"physical_state": "solid"})

    def test_lines_and_samples_change_again_after_the_quotation_is_revised(self):
        order = self.sent_order()
        line = order._catalog_lines()
        sample = order.sample_ids

        order.with_user(self.sales).action_revise_quotation()
        self.assertEqual(order.state, "draft")
        line.with_user(self.sales).write({"price_unit": 1})
        sample.with_user(self.sales).write({"customer_sample_name": "Another sample"})
        extra = self.make_sample(order, "Second sample")
        extra.unlink()

        self.assertEqual(line.price_unit, 1)
        self.assertEqual(sample.customer_sample_name, "Another sample")
        order.with_user(self.sales).action_send_quotation()
        with self.assertRaises(UserError):
            line.write({"price_unit": 2})

    def test_the_advance_invoice_lines_are_not_frozen(self):
        order = self.sent_order()

        self.assertTrue(order.sudo().order_line.filtered("is_downpayment"))
