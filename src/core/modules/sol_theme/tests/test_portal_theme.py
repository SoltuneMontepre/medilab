from lxml import html

from odoo.tests import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestPortalTheme(HttpCase):
    def test_the_portal_header_is_the_back_office_navbar_in_the_theme_colours(self):
        new_test_user(self.env, "portal_theme", groups="base.group_portal")
        self.authenticate("portal_theme", "portal_theme")

        page = html.fromstring(self.url_open("/my").content)

        self.assertEqual(page.xpath("//header[@id='top']/nav/@class"), ["navbar navbar-expand navbar-dark bg-primary"])
        self.assertNotIn("--portal-primary-color", html.tostring(page.find("head"), encoding="unicode"))
