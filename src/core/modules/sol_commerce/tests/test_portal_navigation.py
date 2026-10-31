from odoo.tests import tagged

from .portal_case import PortalCase

SECTIONS = ["/catalog", "/orders", "/support", "/my/account"]
NAVIGATION = "//ul[contains(@class, 'o_medilab_portal_navigation')]"


@tagged("post_install", "-at_install")
class TestPortalNavigation(PortalCase):
    """The portal keeps the catalog, the orders, support and the account apart, one click away from every page."""

    def links(self, path):
        return self.find(self.tree(path), f"{NAVIGATION}//a/@href")

    def test_every_portal_page_links_to_each_section(self):
        order = self.make_order([(self.lead_product, 1)], status="submitted")
        for path in ("/my", "/my/account", "/catalog", "/cart", "/orders", f"/orders/{order.id}", "/support"):
            with self.subTest(path=path):
                self.assertEqual(self.links(path), SECTIONS)

    def test_the_current_section_is_marked(self):
        tree = self.tree("/orders")
        self.assertEqual(self.find(tree, f"{NAVIGATION}//a[contains(@class, 'active')]/@href"), ["/orders"])
        self.assertEqual(self.find(tree, f"{NAVIGATION}//a[@aria-current='page']/@href"), ["/orders"])

    def test_a_visitor_sees_only_the_catalog(self):
        self.authenticate(None, None)
        self.assertEqual(self.links("/catalog"), ["/catalog"])

    def test_the_orders_page_offers_no_support_button(self):
        tree = self.tree("/orders")
        buttons = self.find(tree, "//main//a[contains(@class, 'btn')]/@href")
        self.assertNotIn("/support", buttons)

    def test_the_portal_home_shows_a_support_card(self):
        cards = self.find(
            self.tree("/my"),
            "//div[contains(@class, 'o_portal_index_card') and not(contains(@class, 'd-none'))]/a/@href",
        )
        self.assertIn("/support", cards)

    def test_an_empty_catalog_filter_offers_every_value(self):
        tree = self.tree("/catalog")
        for name, label in (("sample_type", "All sample types"), ("group", "All parameter groups")):
            with self.subTest(name=name):
                select = self.find(tree, f"//select[@name='{name}']")[0]
                self.assertIn("o_medilab_catalog_filter", select.get("class"))
                self.assertEqual(self.find(select, "./option[@value='']/text()"), [label])

    def test_portal_action_buttons_show_an_icon(self):
        self.post("/catalog/add", "/catalog", product_tmpl_id=self.lead_product.id, quantity=1)
        for path, label in (("/my/account", "Upload"), ("/cart", "Submit"), ("/cart", "Save as draft")):
            with self.subTest(path=path, label=label):
                buttons = self.find(self.tree(path), f"//button[normalize-space()='{label}']")
                self.assertTrue(buttons)
                self.assertTrue(self.find(buttons[0], "./iconify-icon"))
