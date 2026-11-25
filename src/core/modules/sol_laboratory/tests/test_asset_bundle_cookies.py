import re

from odoo.tests import HttpCase, new_test_user, tagged

LOGIN = "asset.bundle.reader"
PASSWORD = "asset.bundle.reader.password"
BUNDLE_URL = re.compile(r"/web/assets/[^\"'()\s]+")
SESSION_COOKIE = "session_id"


@tagged("post_install", "-at_install")
class TestAssetBundleCookies(HttpCase):
    def login_page_bundles(self):
        """The bundles the login page loads, and the files, such as icon fonts, its style bundles load."""
        page = self.url_open("/web/login")
        bundles = set(BUNDLE_URL.findall(page.text))
        for css in [url for url in bundles if url.endswith(".css")]:
            bundles |= set(BUNDLE_URL.findall(self.url_open(css).text))
        self.assertTrue(any(url.endswith(".js") for url in bundles), bundles)
        self.assertTrue(any(url.endswith(".woff2") for url in bundles), bundles)
        return page, sorted(bundles)

    def test_a_bundle_requested_without_a_session_sets_no_cookie(self):
        page, bundles = self.login_page_bundles()

        self.assertIn(SESSION_COOKIE, page.cookies)
        self.assertIn("csrf_token", page.text)
        for url in bundles:
            with self.subTest(url=url):
                self.opener.cookies.clear()
                response = self.url_open(url)

                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.content)
                self.assertIn("immutable", response.headers["Cache-Control"])
                self.assertNotIn("Set-Cookie", response.headers)

    def test_a_visitor_signs_in_and_loads_the_bundles(self):
        user = new_test_user(self.env, login=LOGIN, password=PASSWORD)
        page, bundles = self.login_page_bundles()
        csrf_token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        if not csrf_token:
            self.fail("The login page has no CSRF token")

        signed_in = self.url_open(
            "/web/login",
            data={"login": LOGIN, "password": PASSWORD, "csrf_token": csrf_token.group(1)},
            allow_redirects=False,
        )

        self.assertEqual(signed_in.status_code, 303)
        self.assertEqual(signed_in.session.uid, user.id)
        for url in bundles:
            with self.subTest(url=url):
                response = self.url_open(url)

                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.content)
