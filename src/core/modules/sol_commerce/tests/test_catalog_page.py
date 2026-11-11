from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestCatalogPage(HttpCase):
    """A visitor can open the catalog without signing in."""

    def test_visitor_opens_the_catalog(self):
        response = self.url_open("/catalog")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Catalog", response.text)
        self.assertIn("Cart", response.text)

    def test_catalog_shows_why_an_item_was_not_added(self):
        # Adding an item that left the catalog sends the customer back here with the refusal.
        response = self.url_open("/catalog?error=This item is not in the catalog. <b>")

        self.assertEqual(response.status_code, 200)
        self.assertIn("This item is not in the catalog. &lt;b&gt;", response.text)
