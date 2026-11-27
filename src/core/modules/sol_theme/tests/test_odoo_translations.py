from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools.translate import code_translations


@tagged("post_install", "-at_install")
class TestOdooTranslations(TransactionCase):
    def test_odoo_screen_strings_odoo_leaves_untranslated_are_vietnamese(self):
        messages = code_translations.get_web_translations("sol_theme", "vi_VN")["messages"]

        self.assertIn({"id": "Enter your password", "string": "Nhập mật khẩu của bạn"}, messages)
        self.assertIn({"id": "No messages yet.", "string": "Chưa có tin nhắn nào."}, messages)


@tagged("post_install", "-at_install")
class TestPortalOdooTranslations(HttpCase):
    def test_the_portal_reads_the_vietnamese_of_odoo_screen_strings_too(self):
        self.env["res.lang"]._activate_lang("vi_VN")

        response = self.url_open("/website/translations?lang=vi_VN")

        messages = response.json()["modules"]["sol_theme"]["messages"]
        self.assertIn({"id": "No messages yet.", "string": "Chưa có tin nhắn nào."}, messages)
