from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools.misc import format_date

from .portal_case import PortalCase
from odoo.addons.sol_commerce.constants.orders import PORTAL_ORDERS_PER_PAGE


@tagged("post_install", "-at_install")
class TestOrderHistory(PortalCase):
    """Each order history row says what the order is for and when, the list is paged, and drafts are not reordered."""

    def row(self, tree, order):
        rows = self.find(tree, f"//tr[.//a[@href='/orders/{order.id}']]")
        self.assertEqual(len(rows), 1, order.name)
        return rows[0]

    def test_a_row_shows_the_items_and_the_date(self):
        order = self.make_order([(self.lead_product, 1), (self.package_product, 1)], status="submitted")

        row = self.row(self.tree("/orders"), order).text_content()

        self.assertIn(self.lead_product.name, row)
        self.assertIn(self.package_product.name, row)
        self.assertIn(format_date(self.env, order.submitted_at), row)

    def test_the_history_is_paged(self):
        orders = self.env["sale.order"]
        for _index in range(PORTAL_ORDERS_PER_PAGE + 1):
            orders |= self.make_order([(self.lead_product, 1)], status="submitted")
        newest = orders.sorted("id", reverse=True)

        first = self.tree("/orders")
        second = self.tree("/orders/page/2")

        self.assertTrue(self.find(first, "//a[@href='/orders/page/2']"))
        self.row(first, newest[0])
        self.assertFalse(self.find(first, f"//a[@href='/orders/{newest[-1].id}']"))
        self.row(second, newest[-1])

    def test_reorder_is_not_offered_on_a_draft(self):
        draft = self.make_order([(self.lead_product, 1)])
        submitted = self.make_order([(self.lead_product, 1)], status="submitted")

        tree = self.tree("/orders")

        self.assertFalse(self.find(self.row(tree, draft), f".//form[@action='/orders/{draft.id}/reorder']"))
        self.assertTrue(self.find(self.row(tree, submitted), f".//form[@action='/orders/{submitted.id}/reorder']"))
        self.assertFalse(self.find(self.tree(f"/orders/{draft.id}"), f"//form[@action='/orders/{draft.id}/reorder']"))
        with self.assertRaises(UserError):
            draft.with_user(self.portal).action_reorder()
