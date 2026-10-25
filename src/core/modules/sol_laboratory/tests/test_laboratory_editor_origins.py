from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.services.laboratory_editor_page import configured_origin


@tagged("post_install", "-at_install")
class TestLaboratoryEditorOrigins(TransactionCase):
    def test_only_explicit_unambiguous_origins_are_accepted(self):
        for value in (
            None,
            "",
            "//docs.example",
            "javascript:alert(1)",
            "https://user@docs.example",
            "https://@docs.example",
            "https://docs.example/path",
            "https://docs.example?x",
            "https://docs.example#x",
            "https://docs.example\\evil",
            "https://docs.example\n",
            "https://docs.example:%32",
            "https://docs.example:",
            "https://docs.example:0",
            "https://docs.example:99999",
            "http://docs.example",
            "http://127.1",
            "http://0x7f000001",
            "https://docs..example",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                configured_origin(value)

    def test_public_tls_and_loopback_http_and_explicit_private_callback_are_supported(self):
        for value in (
            "https://docs.lab.example",
            "https://docs.lab.example:8443",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "http://[::1]:8080",
        ):
            self.assertEqual(configured_origin(value + "/"), value)
        self.assertEqual(configured_origin("http://odoo:8069", private=True), "http://odoo:8069")
