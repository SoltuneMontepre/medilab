from unittest.mock import patch
from urllib.parse import urlsplit

from odoo.tests import tagged

from .portal_case import PortalCase
from odoo.addons.sol_laboratory.constants.models import MODEL_RES_USERS

ENGLISH = "en_US"
VIETNAMESE = "vi_VN"
SWITCHER = "//li[contains(@class, 'o_medilab_language_switcher')]"


@tagged("post_install", "-at_install")
class TestPortalLanguage(PortalCase):
    """A customer switches the portal language from the header or the account page, and the choice is saved."""

    def setUp(self):
        super().setUp()
        self.portal.lang = ENGLISH

    def switch(self, lang, redirect):
        response = self.post("/my/language", "/my", lang=lang, redirect=redirect)
        self.env.invalidate_all()
        return response

    def languages(self, path):
        tree = self.tree(path)
        languages = self.texts(tree, f"{SWITCHER}//input[@name='lang']/@value")
        return set(languages)

    def test_the_header_offers_every_language(self):
        for path in ("/my", "/orders"):
            with self.subTest(path=path):
                self.assertEqual(self.languages(path), {ENGLISH, VIETNAMESE})

    def test_the_header_is_the_only_language_switcher(self):
        self.assertFalse(self.find(self.tree("/my"), "//*[contains(@class, 'js_language_selector')]"))

    def test_the_account_page_offers_the_language_saved_on_the_profile(self):
        self.portal.lang = VIETNAMESE
        tree = self.tree("/my/account")
        selected = self.texts(tree, "//form[@action='/my/language']//select[@name='lang']/option[@selected]/@value")
        self.assertEqual(selected, [VIETNAMESE])

    def test_switching_saves_the_language_and_returns_to_the_page(self):
        response = self.switch(VIETNAMESE, "/orders?filter=open")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(urlsplit(response.headers["Location"]).path, "/orders")
        self.assertEqual(urlsplit(response.headers["Location"]).query, "filter=open")
        self.assertEqual(self.portal.lang, VIETNAMESE)
        self.assertEqual(self.portal.partner_id.lang, VIETNAMESE)
        for path in ("/my/account", "/orders"):
            with self.subTest(path=path):
                active = self.texts(self.tree(path), f"{SWITCHER}/a/span/text()")
                self.assertEqual(active, ["Tiếng Việt"])

    def test_switching_drops_the_language_prefix_of_the_page(self):
        self.portal.lang = VIETNAMESE
        response = self.switch(ENGLISH, "/vi/my/account")

        self.assertEqual(urlsplit(response.headers["Location"]).path, "/my/account")
        self.assertEqual(self.portal.lang, ENGLISH)

    def test_switching_never_leaves_the_portal(self):
        for redirect in ("https://elsewhere.example/my", "//elsewhere.example/my", "/\\elsewhere.example/my"):
            with self.subTest(redirect=redirect):
                location = self.switch(VIETNAMESE, redirect).headers["Location"]
                self.assertNotEqual(urlsplit(location).netloc, "elsewhere.example")
                self.assertFalse(urlsplit(location).path.startswith(("//", "/\\")))

    def test_a_visitor_keeps_the_choice_in_the_browser_only(self):
        public = self.env.ref("base.public_user")
        public_lang = public.lang
        self.authenticate(None, None)

        response = self.post("/my/language", "/catalog", lang=VIETNAMESE, redirect="/catalog")
        self.env.invalidate_all()

        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.opener.cookies.get("frontend_lang"), VIETNAMESE)
        self.assertEqual(public.lang, public_lang)
        self.assertEqual(self.portal.lang, ENGLISH)

    def test_an_unchanged_language_is_not_written(self):
        users = type(self.env[MODEL_RES_USERS])
        write = users.write
        written = []

        def spy(records, vals):
            written.append(vals)
            return write(records, vals)

        with patch.object(users, "write", spy):
            self.switch(ENGLISH, "/my")

        self.assertFalse([vals for vals in written if "lang" in vals])

    def test_an_unknown_language_changes_nothing(self):
        self.switch("xx_XX", "/my")

        self.assertEqual(self.portal.lang, ENGLISH)
