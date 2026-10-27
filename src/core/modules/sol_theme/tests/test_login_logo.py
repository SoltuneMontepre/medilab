from odoo.tests import HttpCase, tagged
from odoo.tools.binary import BinaryBytes
from odoo.tools.misc import file_path


@tagged("post_install", "-at_install")
class TestLoginLogo(HttpCase):
    def test_the_login_logo_is_a_file_of_the_theme_not_the_company_attachment(self):
        # The login page shows a logo only when the company has one of its own.
        with open(file_path("sol_theme/static/src/img/icons/icon-512x512.png"), "rb") as icon:
            self.env.company.logo = BinaryBytes(icon.read())

        page = self.url_open("/web/login").text

        self.assertIn('src="/sol_theme/static/src/img/icons/icon-192x192.png"', page)
        self.assertNotIn("/web/binary/company_logo", page)

    def test_the_login_logo_file_is_served(self):
        response = self.url_open("/sol_theme/static/src/img/icons/icon-192x192.png")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content)
