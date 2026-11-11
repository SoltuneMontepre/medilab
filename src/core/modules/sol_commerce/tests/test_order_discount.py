from lxml import etree

from odoo.exceptions import UserError
from odoo.tests import Form, tagged
from odoo.tests.form import O2MProxy

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER, MODEL_SALE_ORDER_DISCOUNT
from odoo.addons.sol_commerce.constants.xml_ids import DISCOUNT_PRODUCT, LINE_DISCOUNT_GROUP
from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION
from odoo.addons.sol_laboratory.tests.assertions import assert_instance

LINES = "//page[@name='order_lines']/field[@name='product_line_ids']"
DISCOUNT_BUTTON = "//div[@name='so_button_below_order_lines']/button[@name='action_open_discount_wizard']"


@tagged("post_install", "-at_install")
class TestOrderDiscount(OrderCase):
    """Sales give a percentage discount on a line or on the whole quotation before sending it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The order form also lists the order's support requests.
        cls.sales_person.permission_ids |= cls.env[MODEL_PERMISSION].search([("code", "=", "support.request.read.all")])

    def discount(self, order, kind, percentage):
        wizard = (
            self.env[MODEL_SALE_ORDER_DISCOUNT]
            .with_user(self.sales)
            .with_context(active_id=order.id)
            .create({"discount_type": kind, "discount_percentage": percentage})
        )
        return wizard.action_apply_discount()

    def form_arch(self, user):
        return etree.fromstring(self.env[MODEL_SALE_ORDER].with_user(user).get_view(view_type="form")["arch"])

    def test_sales_hold_the_line_discount(self):
        self.assertTrue(self.sales.has_group(LINE_DISCOUNT_GROUP))

    def test_the_order_form_shows_sales_the_discount_column_and_button(self):
        arch = self.form_arch(self.sales)

        self.assertTrue(arch.xpath(f"{LINES}/list/field[@name='discount']"))
        buttons = arch.xpath(f"{DISCOUNT_BUTTON}[not(@disabled)]")
        assert isinstance(buttons, list)
        self.assertEqual(len(buttons), 1)

    def test_the_discount_button_is_hidden_once_the_quotation_is_sent(self):
        buttons = self.form_arch(self.sales).xpath(f"{DISCOUNT_BUTTON}[not(@disabled)]")
        assert isinstance(buttons, list)
        button = buttons[0]
        assert isinstance(button, etree._Element)

        self.assertIn("state != 'draft'", button.get("invisible") or "")

    def test_a_salesperson_gives_a_line_a_discount(self):
        order = self.make_quotable_order()
        with Form(order.with_user(self.sales)) as form, assert_instance(form.product_line_ids, O2MProxy).edit(0) as line:
            line.discount = 10

        self.assertEqual(order.order_line.discount, 10)
        self.assertEqual(order.amount_untaxed, self.lead_product.list_price * 0.9)

    def test_a_salesperson_gives_every_line_the_same_discount(self):
        order = self.make_quotable_order([(self.lead_product, 1), (self.package_product, 1)])

        self.discount(order, "sol_discount", 0.15)

        self.assertEqual(order._catalog_lines().mapped("discount"), [15, 15])

    def test_a_salesperson_gives_the_whole_quotation_a_discount_line(self):
        order = self.make_quotable_order([(self.lead_product, 2)])
        before = order.amount_untaxed

        self.discount(order, "so_discount", 0.1)

        line = order.order_line.filtered(lambda line: line.product_id == self.env.ref(DISCOUNT_PRODUCT))
        self.assertEqual(len(line), 1)
        self.assertEqual(line.price_subtotal, -before * 0.1)
        self.assertEqual(order.amount_untaxed, before * 0.9)
        self.assertEqual(order._catalog_lines().mapped("discount"), [0])

    def test_a_discount_on_every_line_leaves_the_discount_line_and_down_payments_alone(self):
        order = self.make_quotable_order([(self.lead_product, 2)])
        self.discount(order, "so_discount", 0.1)
        down_payment = self.env["sale.order.line"].create(
            {"order_id": order.id, "name": "Advance", "price_unit": 1000, "product_uom_qty": 0, "is_downpayment": True}
        )

        self.discount(order, "sol_discount", 0.2)

        self.assertEqual(order._catalog_lines().mapped("discount"), [20])
        self.assertEqual(order._discount_lines().discount, 0)
        self.assertEqual(down_payment.discount, 0)

    def test_a_quotation_with_a_discount_line_is_sent_and_confirmed(self):
        order = self.make_quotable_order()
        self.discount(order, "so_discount", 0.1)

        order.with_user(self.sales).action_send_quotation()
        self.pay_advance(order)
        order.with_user(self.sales).action_confirm_order()

        self.assertEqual(order._latest_quotation().amount_total, order.amount_total)
        self.assertEqual(order.order_status, "confirmed")

    def test_a_fixed_amount_discount_is_not_offered(self):
        kinds = self.env[MODEL_SALE_ORDER_DISCOUNT]._fields["discount_type"].get_values(self.env)

        self.assertEqual(sorted(kinds), ["so_discount", "sol_discount"])

    def test_a_sent_quotation_takes_no_discount(self):
        order = self.sent_order()

        with self.assertRaises(UserError):
            self.discount(order, "sol_discount", 0.1)
        self.assertEqual(order._catalog_lines().mapped("discount"), [0])
