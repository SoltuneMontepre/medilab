import re
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_QUOTATION


@tagged("post_install", "-at_install")
class TestQuotationSend(OrderCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tax_10 = cls.env["account.tax"].create({"name": "Test VAT 10", "amount": 10, "type_tax_use": "sale"})
        cls.tax_8 = cls.env["account.tax"].create({"name": "Test VAT 8", "amount": 8, "type_tax_use": "sale"})

    def send(self, order):
        order.with_user(self.sales).action_send_quotation()
        return order._latest_quotation()

    def test_cannot_send_without_a_catalog_line(self):
        order = self.make_order([], status="claimed", user_id=self.sales.id)

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_send_quotation()

        self.assertFalse(order.quotation_ids)

    def test_cannot_send_when_a_catalog_line_has_no_sample(self):
        order = self.make_order(
            [(self.lead_product, 1), (self.package_product, 1)], status="claimed", user_id=self.sales.id
        )
        order._catalog_lines().filtered(
            lambda line: line.product_id.product_tmpl_id == self.lead_product
        ).sample_id = self.make_sample(order)

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_send_quotation()
        order._catalog_lines().sample_id = order.sample_ids
        self.send(order)

        self.assertEqual(len(order.quotation_ids), 1)

    def test_send_stores_the_numbered_pdf_and_the_deadline(self):
        order = self.make_quotable_order()
        before = fields.Datetime.now()

        quotation = self.send(order)

        self.assertEqual(quotation.status, "sent")
        self.assertEqual(quotation.revision, 1)
        self.assertEqual(quotation.amount_total, order.amount_total)
        self.assertRegex(quotation.code, r"^\d{4} \d{2}/BG-VTT$")
        self.assertTrue(quotation.attachment_id.raw)
        self.assertEqual(quotation.attachment_id.res_id, quotation.id)
        self.assertGreaterEqual(order.payment_deadline, before + timedelta(days=3) - timedelta(seconds=1))
        self.assertEqual(order.order_status, "claimed")
        self.assertEqual(order.quotation_follow_up, "unpaid")

    def test_send_keeps_a_deadline_sales_set(self):
        order = self.make_quotable_order()
        deadline = fields.Datetime.now() + timedelta(days=10)
        order.payment_deadline = deadline

        self.send(order)

        self.assertEqual(order.payment_deadline, deadline)

    def test_catalog_changes_after_sending_do_not_change_the_line(self):
        self.lead_product.taxes_id = self.tax_10
        order = self.make_quotable_order()
        line = order._catalog_lines()
        price = line.price_unit
        self.assertEqual(line.tax_ids, self.tax_10)
        self.send(order)

        self.lead_price.list_price = price + 5000
        self.lead_product.taxes_id = self.tax_8
        line.with_context(sale_write_from_compute=True).technical_price_unit = line.price_unit
        self.env.add_to_compute(line._fields["price_unit"], line)
        self.env.add_to_compute(line._fields["tax_ids"], line)
        line.flush_recordset()
        line.invalidate_recordset()

        self.assertEqual(self.lead_product.list_price, price + 5000)
        self.assertEqual(line.price_unit, price)
        self.assertEqual(line.tax_ids, self.tax_10)

    def test_a_replaced_quotation_cannot_be_sent(self):
        order = self.make_quotable_order()
        first = self.send(order)
        order.with_user(self.sales).action_revise_quotation()
        second = self.send(order)

        with self.assertRaises(UserError):
            first.action_send()

        self.assertEqual(first.status, "replaced")
        self.assertEqual((first.revision, second.revision), (1, 2))
        self.assertEqual(second.replaces_id, first)
        self.assertEqual(second.status, "sent")
        self.assertNotEqual(first.code, second.code)
        self.assertTrue(re.match(r"^\d{4} \d{2}/BG-VTT$", second.code))
        with self.assertRaises(UserError):
            first.write({"status": "sent"})
        self.assertEqual(len(order.quotation_ids), 2)
        self.assertEqual(self.env[MODEL_QUOTATION].search_count([("order_id", "=", order.id)]), 2)

    def test_a_sent_quotation_is_revised_before_it_is_sent_again(self):
        order = self.make_quotable_order()
        self.send(order)

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_send_quotation()
        order.with_user(self.sales).action_revise_quotation()
        self.send(order)

        self.assertEqual(order.quotation_ids.sorted("revision").mapped("revision"), [1, 2])

    def test_revising_needs_a_sent_quotation(self):
        order = self.make_quotable_order()

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_revise_quotation()
