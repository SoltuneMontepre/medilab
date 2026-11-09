from urllib.parse import urlparse

from odoo.tests import tagged

from .portal_case import PortalCase
from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import PORTAL_ORDERS_PER_PAGE
from odoo.addons.sol_commerce.models.orders.sale_order_customer import CUSTOMER_STATUSES


@tagged("post_install", "-at_install")
class TestOrderHistoryFilters(PortalCase):
    """The order history narrows by customer-facing status and by order number, parameter or package before it is
    counted and paged, keeps the filters across pages, orders and Reorder, and tells a filter that matches nothing apart
    from a customer with no orders."""

    def listed(self, path):
        """The orders the order history page lists, top to bottom."""
        hrefs = self.texts(self.tree(path), "//table//td/a/@href")
        return self.env[MODEL_SALE_ORDER].browse([int(urlparse(href).path.rsplit("/", 1)[1]) for href in hrefs])

    def confirmed_with_request(self, status):
        order = self.make_confirmed_order()
        order.test_request_id.sudo().status = status
        return order

    def test_each_status_finds_the_orders_the_customer_sees_under_it(self):
        orders = (
            self.make_order([(self.lead_product, 1)])
            | self.make_order([(self.lead_product, 1)], status="submitted")
            | self.sent_order()
            | self.make_confirmed_order()
            | self.confirmed_with_request("testing")
            | self.confirmed_with_request("reported")
            | self.make_order([(self.lead_product, 1)], status="completed")
            | self.make_order([(self.lead_product, 1)], status="cancelled")
        )
        shown = {order: order.customer_status for order in orders}
        self.assertEqual(set(shown.values()), set(dict(CUSTOMER_STATUSES)))

        for status, _label in CUSTOMER_STATUSES:
            with self.subTest(status=status):
                expected = orders.filtered(lambda order, status=status: shown[order] == status)
                found = orders.search([("id", "in", orders.ids), ("customer_status", "=", status)])
                self.assertEqual(found, expected)
                others = orders.search([("id", "in", orders.ids), ("customer_status", "!=", status)])
                self.assertEqual(others, orders - expected)

    def test_the_status_filter_narrows_the_list_and_the_pager(self):
        submitted = self.env[MODEL_SALE_ORDER]
        for _index in range(PORTAL_ORDERS_PER_PAGE + 1):
            submitted |= self.make_order([(self.lead_product, 1)], status="submitted")
        cancelled = self.make_order([(self.lead_product, 1)], status="cancelled")

        tree = self.tree("/orders?status=cancelled")

        self.assertEqual(self.listed("/orders?status=cancelled"), cancelled)
        self.assertFalse(self.find(tree, "//a[contains(@href, '/orders/page/2')]"))
        self.assertEqual(self.texts(tree, "//select[@name='status']/option[@selected]/@value"), ["cancelled"])
        first = self.tree("/orders?status=submitted")
        self.assertTrue(self.find(first, "//a[@href='/orders/page/2?status=submitted']"))
        self.assertEqual(self.listed("/orders/page/2?status=submitted"), submitted.sorted("id")[:1])

    def test_an_empty_status_filter_reads_all_statuses(self):
        self.make_order([(self.lead_product, 1)], status="submitted")

        select = self.find(self.tree("/orders?status=unknown"), "//select[@name='status']")[0]

        self.assertIn("o_medilab_catalog_filter", select.get("class"))
        self.assertEqual(self.texts(select, "./option[@value='']/text()"), ["All statuses"])
        self.assertFalse(self.texts(select, "./option[@selected]/@value"))

    def test_search_finds_the_order_number_and_the_ordered_items(self):
        lead = self.make_order([(self.lead_product, 1)], status="submitted")
        package = self.make_order([(self.package_product, 1)], status="submitted")

        self.assertEqual(self.listed(f"/orders?search={lead.name}"), lead)
        self.assertEqual(self.listed(f"/orders?search={self.package.name}"), package)
        # The parameters inside a package are not what the customer ordered.
        self.assertEqual(self.listed(f"/orders?search={self.other.name}"), self.env[MODEL_SALE_ORDER])
        both = f"/orders?search={self.parameter.name}&status=cancelled"
        self.assertEqual(self.listed(both), self.env[MODEL_SALE_ORDER])

    def test_orders_and_reorder_keep_the_filters(self):
        order = self.make_order([(self.lead_product, 1)], status="submitted")
        query = f"?status=submitted&search={order.name}"

        row = self.find(self.tree(f"/orders{query}"), f"//tr[.//a[@href='/orders/{order.id}{query}']]")
        self.assertEqual(len(row), 1)
        back = self.texts(self.tree(f"/orders/{order.id}{query}"), "//main//a[i[@data-icon='arrow_back']]/@href")
        self.assertEqual(back, [f"/orders{query}"])

        response = self.post(f"/orders/{order.id}/reorder", f"/orders{query}", status="submitted", search=order.name)

        new = self.env[MODEL_SALE_ORDER].search([("reordered_from_id", "=", order.id)])
        location = urlparse(response.headers["Location"])
        self.assertEqual(f"{location.path}?{location.query}", f"/orders/{new.id}{query}")

    def test_a_filter_matching_nothing_offers_to_clear_it(self):
        self.make_order([(self.lead_product, 1)], status="submitted")

        tree = self.tree("/orders?status=completed")

        self.assertIn("No orders match these filters.", tree.text_content())
        self.assertTrue(self.find(tree, "//main//p/a[@href='/orders']"))
        self.assertNotIn("No orders yet", tree.text_content())

    def test_a_customer_without_orders_sees_no_filters(self):
        tree = self.tree("/orders?status=completed")

        self.assertIn("No orders yet.", tree.text_content())
        self.assertFalse(self.find(tree, "//select[@name='status']"))
