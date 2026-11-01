import re

from lxml import html

from odoo.tests import HttpCase

from .order_case import OrderCase
from odoo.addons.sol_laboratory.tests.assertions import assert_instance

PASSWORD = "portal-orders-pass-1"


class PortalCase(HttpCase, OrderCase):
    """The order customer's contact signed in to the portal."""

    def setUp(self):
        super().setUp()
        self.portal.password = PASSWORD
        self.authenticate(self.portal.login, PASSWORD)

    def page(self, path):
        response = self.url_open(path)
        self.assertEqual(response.status_code, 200)
        return response.text

    def tree(self, path):
        return assert_instance(html.fromstring(self.page(path)), html.HtmlElement)

    def find(self, node: html.HtmlElement, path: str) -> list[html.HtmlElement]:
        """The elements an XPath matches, which lxml types as a union with its scalar results."""
        found = node.xpath(path)
        if not isinstance(found, list):
            self.fail(f"{path} matches no elements.")
        return [assert_instance(element, html.HtmlElement) for element in found]

    def texts(self, node: html.HtmlElement, path: str) -> list[str]:
        """The attribute values or texts an XPath matches."""
        found = node.xpath(path)
        if not isinstance(found, list):
            self.fail(f"{path} matches no values.")
        return [str(assert_instance(value, str)) for value in found]

    def csrf_token(self, path):
        match = re.search(r'name="csrf_token" value="([^"]+)"', self.page(path))
        if match is None:
            self.fail(f"{path} has no CSRF token.")
        return match.group(1)

    def post(self, path, page, **data):
        return self.url_open(path, data={"csrf_token": self.csrf_token(page), **data}, allow_redirects=False)
