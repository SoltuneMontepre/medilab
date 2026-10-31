from odoo.tests import tagged

from .portal_case import PortalCase

VIETNAMESE = "vi_VN"
ORDERS_IN_VIETNAMESE = "Đơn Hàng"


@tagged("post_install", "-at_install")
class TestPortalLanguage(PortalCase):
    """A customer switches the portal's language from their account; it applies at once, on every page, and stays."""

    def save_language(self, lang):
        return self.post("/my/language", "/my/account", lang=lang)

    def test_the_account_page_offers_the_installed_languages(self):
        options = self.tree("/my/account").xpath("//form[@action='/my/language']//option/@value")

        self.assertEqual(set(options), {code for code, _name in self.env["res.lang"].get_installed()})

    def test_a_saved_language_is_remembered_and_shown_at_once(self):
        response = self.save_language(VIETNAMESE)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.portal.lang, VIETNAMESE)
        self.assertEqual(self.contact.lang, VIETNAMESE)
        self.assertIn(ORDERS_IN_VIETNAMESE, self.page("/orders"))

    def test_a_language_that_is_not_installed_is_refused(self):
        lang = self.portal.lang

        self.save_language("fr_FR")

        self.assertEqual(self.portal.lang, lang)

    def test_the_order_pages_follow_the_language_in_the_address(self):
        self.assertIn(ORDERS_IN_VIETNAMESE, self.page("/vi/orders"))
