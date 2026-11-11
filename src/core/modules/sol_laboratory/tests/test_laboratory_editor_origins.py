from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.services.laboratory_editor_page import EDITOR_PATH, configured_origin


@tagged("post_install", "-at_install")
class TestLaboratoryEditorOrigins(TransactionCase):
    def test_editor_path_accepts_only_ascii_identifiers(self):
        self.assertIsNotNone(EDITOR_PATH.fullmatch("/medilab/laboratory-files/17/edit"))
        for identifier in ("١٧", "１７", "1٧"):
            with self.subTest(identifier=identifier):
                self.assertIsNone(EDITOR_PATH.fullmatch(f"/medilab/laboratory-files/{identifier}/edit"))

    def test_unicode_numeric_host_labels_do_not_change_origin_validation(self):
        for host in ("127.١", "127.１", "0x７f000001", "docs.١٧", "docs.１７"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                configured_origin("https://" + host)
        with self.assertRaisesRegex(ValueError, "Ambiguous IP address"):
            configured_origin("https://docs.17")
        self.assertEqual(configured_origin("https://docs.v17"), "https://docs.v17")

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
