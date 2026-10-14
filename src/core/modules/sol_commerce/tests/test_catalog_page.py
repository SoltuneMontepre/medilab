from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestCatalogPage(HttpCase):
    """A visitor can open the catalog without signing in."""

    def test_visitor_opens_the_catalog(self):
        response = self.url_open("/catalog")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Catalog", response.text)
        self.assertIn("Cart", response.text)
