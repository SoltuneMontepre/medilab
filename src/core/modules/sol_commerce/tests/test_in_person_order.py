from odoo.exceptions import UserError
from odoo.tests import tagged

from .order_case import OrderCase


@tagged("post_install", "-at_install")
class TestInPersonOrder(OrderCase):
    """Sales shows or prints the quotation to a customer at the counter and confirms the order once it is paid, or at
    once without an advance; every order's balance is due before the report by default."""

    def sales_order(self, **vals):
        order = self.make_quotable_order()
        order.write({"source": "sales", **vals})
        return order

    def test_a_portal_order_pays_its_balance_before_the_report_by_default(self):
        order = self.make_order([(self.lead_product, 1)])

        self.assertEqual(order.balance_due, "before_report")

    def test_an_order_sales_creates_pays_its_balance_before_the_report_by_default(self):
        order = (
            self.env["sale.order"]
            .with_user(self.sales)
            .with_context(medilab_sales_order=True)
            .create({"partner_id": self.contact.id, "customer_id": self.customer.id})
        )

        self.assertEqual(order.balance_due, "before_report")

    def test_sales_confirms_its_order_without_an_advance_without_the_customer_accepting(self):
        order = self.sales_order(advance_method="none", user_id=self.head.id)
        order.with_user(self.head).action_send_quotation()

        order.with_user(self.head).action_confirm_order()

        self.assertEqual(order.order_status, "confirmed")
        self.assertEqual(order._latest_quotation().status, "accepted")
        # The balance requested on confirmation is no advance.
        self.assertEqual(order.quotation_follow_up, "accepted")

    def test_paying_the_advance_at_the_counter_lets_sales_confirm(self):
        order = self.sales_order()
        order.with_user(self.sales).action_send_quotation()

        with self.assertRaisesRegex(UserError, "accept the quotation"):
            order.with_user(self.sales).action_confirm_order()
        self.pay_advance(order)
        order.with_user(self.sales).action_confirm_order()

        self.assertEqual(order.order_status, "confirmed")

    def test_a_portal_order_without_an_advance_still_waits_for_the_customer(self):
        order = self.make_quotable_order()
        order.write({"advance_method": "none", "user_id": self.head.id})
        order.with_user(self.head).action_send_quotation()

        with self.assertRaisesRegex(UserError, "accept the quotation"):
            order.with_user(self.head).action_confirm_order()

    def test_print_opens_the_quotation_as_sent(self):
        order = self.sales_order()
        order.with_user(self.sales).action_send_quotation()

        action = order.with_user(self.sales).action_print_quotation()

        self.assertEqual(action["url"], f"/web/content/{order._latest_quotation().attachment_id.id}")

    def test_an_unsent_quotation_cannot_be_printed(self):
        order = self.sales_order()

        with self.assertRaisesRegex(UserError, "Send the quotation"):
            order.with_user(self.sales).action_print_quotation()
