from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_PRODUCT_TEMPLATE
from odoo.addons.sol_commerce.constants.xml_ids import PUBLIC_PARTNER
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TYPE


@tagged("post_install", "-at_install")
class TestOrderCart(OrderCase):
    def test_submitting_requires_a_line(self):
        order = self.make_order([])

        with self.assertRaises(UserError):
            order.action_submit()

    def test_cart_total_excludes_vat_and_uses_the_package_price(self):
        order = self.make_order([(self.lead_product, 2), (self.package_product, 1)])
        package_line = order._catalog_lines().filtered(
            lambda line: line.product_id.product_tmpl_id == self.package_product
        )

        self.assertEqual(order.catalog_total, self.lead_product.list_price * 2 + self.package.list_price)
        self.assertEqual(package_line.price_unit, self.package.list_price)
        self.assertGreater(self.package.parts_price, self.package.list_price)
        self.assertNotEqual(package_line.price_unit, self.package.parts_price)

    def test_visitor_submit_requires_an_email_and_creates_the_contact(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.env.ref(PUBLIC_PARTNER).id,
                "source": "portal",
                "order_status": "draft",
                "user_id": False,
                "order_line": [
                    Command.create({"product_id": self.lead_product.product_variant_ids.id, "product_uom_qty": 1})
                ],
            }
        )

        with self.assertRaises(UserError):
            order.action_submit({"name": "Tran Thi Lan"})
        order.action_submit({"name": "Tran Thi Lan", "email": "lan@example.com", "phone": "0901 000 111"})

        self.assertEqual(order.order_status, "submitted")
        self.assertEqual(order.customer_id.email, "lan@example.com")
        self.assertFalse(order.user_id)

    def test_reorder_uses_current_prices_and_leaves_the_original(self):
        order = self.make_order([(self.lead_product, 2), (self.package_product, 1)], status="completed")
        original_price = (
            order._catalog_lines()
            .filtered(lambda line: line.product_id.product_tmpl_id == self.lead_product)
            .price_unit
        )
        invoices = order.invoice_ids
        self.lead_price.list_price = original_price + 5000
        self.package.action_archive()

        new = order.with_user(self.portal).action_reorder()

        self.assertEqual(order.order_status, "completed")
        self.assertEqual(order.invoice_ids, invoices)
        self.assertEqual(
            order._catalog_lines()
            .filtered(lambda line: line.product_id.product_tmpl_id == self.lead_product)
            .price_unit,
            original_price,
        )
        self.assertEqual(new.order_status, "draft")
        self.assertFalse(new.user_id)
        self.assertEqual(new.reordered_from_id, order)
        self.assertEqual(new._catalog_lines().price_unit, original_price + 5000)
        self.assertEqual(new._catalog_lines().product_id.product_tmpl_id, self.lead_product)
        self.assertIn(self.package.name, (new.reorder_note or ""))

    def test_archiving_a_price_on_an_open_order_is_refused(self):
        self.make_order([(self.lead_product, 1)])

        with self.assertRaises(UserError):
            self.lead_price.action_archive()

    def test_portal_customer_cannot_change_a_price(self):
        order = self.make_order([(self.lead_product, 1)])

        with self.assertRaises(AccessError):
            order.order_line.with_user(self.portal).write({"price_unit": 1})
        with self.assertRaises(AccessError):
            order.with_user(self.portal).write({"order_status": "claimed", "user_id": self.portal.id})
        self.assertEqual(order.order_line.price_unit, self.lead_product.list_price)

    def test_catalog_filters_by_name_price_and_sample_type(self):
        sample = self.env[MODEL_SAMPLE_TYPE].create({"name": "Bottled water", "code": "LM-CART"})
        self.offer(self.parameter, sample)
        products = self.env[MODEL_PRODUCT_TEMPLATE]

        found = products.search(
            products._catalog_domain(sample_type=sample, name="Lead", price_min=1000, price_max=200000)
        )

        self.assertIn(self.lead_product, found)
        self.assertNotIn(self.package_product, found)
