import os
from unittest.mock import patch

from odoo.tests import BaseCase, tagged

from odoo.addons.sol_laboratory.constants.laboratory_editing import INTERNAL_URL_VARIABLE
from odoo.addons.sol_laboratory.services.editing_service_urls import is_editing_service_url, is_saved_document_url

SERVICE = "http://onlyoffice"
SAVED = "http://onlyoffice/cache/files/data/Khirz6zTPdfd7/output.xlsx/output.xlsx?md5=abc&expires=1"


@tagged("post_install", "-at_install")
class TestEditingServiceUrls(BaseCase):
    def test_a_saved_document_is_fetched_from_the_editing_service(self):
        for url, service in (
            (SAVED, SERVICE),
            (SAVED, "http://onlyoffice/"),
            ("http://onlyoffice:80/cache/output.docx", SERVICE),
            ("HTTP://OnlyOffice/cache/output.docx", SERVICE),
            ("https://docs.lab.internal:8443/cache/output.pptx", "https://docs.lab.internal:8443"),
            ("https://docs.lab.internal/cache/output.pptx", "https://docs.lab.internal:443"),
        ):
            with self.subTest(url=url, service=service):
                self.assertTrue(is_editing_service_url(url, service))

    def test_a_saved_document_is_never_fetched_from_anywhere_else(self):
        for url in (
            "http://odoo:8069/web/database/manager",
            "http://onlyoffice.attacker.example/output.xlsx",
            "http://attacker.example/onlyoffice/output.xlsx",
            "http://attacker.example/?host=onlyoffice",
            "http://onlyoffice@attacker.example/output.xlsx",
            "http://user:secret@onlyoffice/output.xlsx",
            "https://onlyoffice/output.xlsx",
            "http://onlyoffice:8080/output.xlsx",
            "http://onlyoffice:port/output.xlsx",
            "http://169.254.169.254/latest/meta-data/",
            "http://127.0.0.1/output.xlsx",
            "ftp://onlyoffice/output.xlsx",
            "file:///etc/passwd",
            "//onlyoffice/output.xlsx",
            "onlyoffice/output.xlsx",
            "http://onlyoffice\\@attacker.example/output.xlsx",
            " http://onlyoffice/output.xlsx",
            "http://onlyoffice/output.xlsx\r\nHost: attacker.example",
            "http://onlyoffice\t/output.xlsx",
            "",
            None,
        ):
            with self.subTest(url=url):
                self.assertFalse(is_editing_service_url(url, SERVICE))

    def test_nothing_is_fetched_without_the_editing_service_address(self):
        for service in ("", None, "onlyoffice", "ftp://onlyoffice"):
            with self.subTest(service=service):
                self.assertFalse(is_editing_service_url(SAVED, service))

    def test_the_editing_service_address_comes_from_the_environment(self):
        with patch.dict(os.environ, {INTERNAL_URL_VARIABLE: SERVICE}):
            self.assertTrue(is_saved_document_url(SAVED))
            self.assertFalse(is_saved_document_url("http://attacker.example/output.xlsx"))
        with patch.dict(os.environ, clear=False):
            os.environ.pop(INTERNAL_URL_VARIABLE, None)
            self.assertFalse(is_saved_document_url(SAVED))
