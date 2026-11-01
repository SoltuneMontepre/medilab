from odoo.fields import Command
from odoo.tests import tagged

from .portal_case import PASSWORD, PortalCase
from odoo.addons.sol_laboratory.services.record_id import persisted_id

SECTIONS = ["/catalog", "/orders", "/support", "/my/account"]
NAVIGATION = "//ul[contains(@class, 'o_medilab_portal_navigation')]"
VISIBLE_CARDS = "//div[contains(@class, 'o_portal_index_card') and not(contains(@class, 'd-none'))]/a/@href"
# Buttons that act without an icon: closing a dialog, and the cart's quantity steppers.
SILENT_BUTTONS = ("−", "+")


@tagged("post_install", "-at_install")
class TestPortalNavigation(PortalCase):
    """The portal keeps the catalog, the orders, support and the account apart, one click away from every page."""

    def links(self, path):
        return self.texts(self.tree(path), f"{NAVIGATION}//a/@href")

    def test_every_portal_page_links_to_each_section(self):
        order = self.make_order([(self.lead_product, 1)], status="submitted")
        for path in ("/my", "/my/account", "/catalog", "/cart", "/orders", f"/orders/{order.id}", "/support"):
            with self.subTest(path=path):
                self.assertEqual(self.links(path), SECTIONS)

    def test_the_current_section_is_marked(self):
        tree = self.tree("/orders")
        self.assertEqual(self.texts(tree, f"{NAVIGATION}//a[contains(@class, 'active')]/@href"), ["/orders"])
        self.assertEqual(self.texts(tree, f"{NAVIGATION}//a[@aria-current='page']/@href"), ["/orders"])

    def test_a_visitor_sees_the_catalog_link_only_in_the_catalog(self):
        self.authenticate(None, None)
        self.assertEqual(self.links("/catalog"), ["/catalog"])
        self.assertEqual(self.links("/verify"), [])

    def test_a_portal_user_who_is_not_a_customer_sees_no_customer_section(self):
        partner = self.env["res.partner"].create({"name": "Phong Thi Nghiem Doi Tac", "email": "partner@lab.example"})
        user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": partner.name,
                    "login": "portal.partner",
                    "partner_id": partner.id,
                    "password": PASSWORD,
                    "group_ids": [Command.set([persisted_id(self.env.ref("base.group_portal"))])],
                }
            )
        )
        self.authenticate(user.login, PASSWORD)

        tree = self.tree("/my")
        self.assertEqual(self.texts(tree, f"{NAVIGATION}//a/@href"), [])
        self.assertNotIn("/support", self.texts(tree, VISIBLE_CARDS))

    def test_the_orders_page_offers_no_support_button(self):
        tree = self.tree("/orders")
        buttons = self.texts(tree, "//main//a[contains(@class, 'btn')]/@href")
        self.assertNotIn("/support", buttons)

    def test_the_portal_home_shows_a_support_card(self):
        self.assertIn("/support", self.texts(self.tree("/my"), VISIBLE_CARDS))

    def test_an_empty_catalog_filter_offers_every_value(self):
        tree = self.tree("/catalog")
        for name, label in (("sample_type", "All sample types"), ("group", "All parameter groups")):
            with self.subTest(name=name):
                select = self.find(tree, f"//select[@name='{name}']")[0]
                self.assertIn("o_medilab_catalog_filter", select.get("class"))
                self.assertEqual(self.texts(select, "./option[@value='']/text()"), [label])

    def test_portal_action_buttons_show_an_icon(self):
        order = self.sent_order()
        self.post("/catalog/add", "/catalog", product_tmpl_id=self.lead_product.id, quantity=1)
        for path in ("/my/account", "/cart", f"/orders/{order.id}", "/support/new"):
            buttons = [
                button
                for button in self.find(self.tree(path), "//main//*[self::a or self::button][contains(@class, 'btn')]")
                if "btn-close" not in button.get("class", "")
                and not button.get("data-bs-dismiss")
                and button.text_content().strip() not in SILENT_BUTTONS
            ]
            self.assertTrue(buttons, path)
            for button in buttons:
                with self.subTest(path=path, label=button.text_content().strip()):
                    self.assertTrue(self.find(button, "./i[contains(@class, 'oi')]"))
