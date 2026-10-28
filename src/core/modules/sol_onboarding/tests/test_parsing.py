import socket
from io import BytesIO
from unittest.mock import patch

import requests

from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open
from odoo.tools.pdf import PdfReader

from odoo.addons.sol_onboarding.services.parsing import clean_text, html_tree, json_data, pdf_text


@tagged("post_install", "-at_install")
class TestParsing(TransactionCase):
    def test_clean_text_removes_control_characters_and_folds_spaces(self):
        self.assertEqual(clean_text(" TCVN\u00a06492\uff1a2011\x00\t "), "TCVN 6492\uff1a2011")

    def test_clean_text_keeps_the_characters_of_the_source(self):
        for value in ("10⁶ CFU/g", "SO₄²⁻", "mg/m³"):
            with self.subTest(value=value):
                self.assertEqual(clean_text(value), value)

    def test_html_is_parsed_without_fetching_anything(self):
        body = b'<script src="https://evil.test/x.js"></script><link href="https://evil.test/a.css"><p>A</p>'
        with (
            patch.object(requests.Session, "get", side_effect=AssertionError("fetched")),
            patch.object(socket.socket, "connect", side_effect=AssertionError("network")),
        ):
            tree = html_tree(body)
        self.assertEqual(tree.text_content().strip(), "A")

    def test_pdf_text_reads_a_text_pdf(self):
        with file_open("sol_onboarding/tests/pages/scope.pdf", "rb") as scope:
            self.assertIn("TCVN 6492:2011", pdf_text(scope.read()))

    def test_a_pdf_without_text_gives_no_text(self):
        with file_open("sol_onboarding/tests/pages/scanned.pdf", "rb") as scanned:
            body = scanned.read()
        self.assertEqual(len(PdfReader(BytesIO(body), strict=False).pages), 1)
        self.assertEqual(pdf_text(body), "")

    def test_a_broken_pdf_gives_no_text(self):
        self.assertEqual(pdf_text(b"not a pdf"), "")

    def test_json_is_decoded(self):
        self.assertEqual(json_data('{"a": "Nước"}'.encode()), {"a": "Nước"})
