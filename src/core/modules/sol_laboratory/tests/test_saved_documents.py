import os
from unittest.mock import patch

import requests

from odoo.tests import BaseCase, tagged

from .editing_service import PUBLIC_URL, LocalEditingService
from odoo.addons.sol_laboratory.constants.laboratory_editing import INTERNAL_URL_VARIABLE, PUBLIC_URL_VARIABLE
from odoo.addons.sol_laboratory.services import saved_documents
from odoo.addons.sol_laboratory.services.saved_documents import (
    SavedDocumentRefused,
    SavedDocumentTooLarge,
    SavedDocumentUnavailable,
    saved_document,
)

SAVED_PATH = "/cache/files/data/Khirz6zTPdfd7_902/output.xlsx/output.xlsx"
QUERY = "?md5=abc&expires=1&filename=output.xlsx"
CONTENT = "Kết quả HPLC, sửa trực tuyến".encode() * 100


@tagged("post_install", "-at_install")
class TestSavedDocuments(BaseCase):
    def setUp(self):
        super().setUp()
        self.service = LocalEditingService(self)
        environment = patch.dict(os.environ, {INTERNAL_URL_VARIABLE: self.service.url, PUBLIC_URL_VARIABLE: PUBLIC_URL})
        environment.start()
        self.addCleanup(environment.stop)

    def read_saved_document(self, url):
        with saved_document(url) as chunks:
            return b"".join(chunks)

    def test_a_saved_document_on_the_public_address_is_streamed_from_the_internal_one(self):
        self.service.answer(SAVED_PATH, CONTENT)

        self.assertEqual(self.read_saved_document(f"{PUBLIC_URL}{SAVED_PATH}{QUERY}"), CONTENT)
        self.assertEqual(self.service.asked, [f"{SAVED_PATH}{QUERY}"])

    def test_a_saved_document_on_the_internal_address_is_streamed_from_it(self):
        self.service.answer(SAVED_PATH, CONTENT)

        self.assertEqual(self.read_saved_document(f"{self.service.url}{SAVED_PATH}{QUERY}"), CONTENT)

    def test_a_saved_document_comes_in_chunks(self):
        self.service.answer(SAVED_PATH, CONTENT, headers={"Transfer-Encoding": "chunked"})

        with patch.object(saved_documents, "CHUNK_SIZE", 512), saved_document(f"{PUBLIC_URL}{SAVED_PATH}") as chunks:
            parts = list(chunks)

        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= 512 for part in parts))
        self.assertEqual(b"".join(parts), CONTENT)

    def test_an_address_on_any_other_origin_is_never_fetched(self):
        for url in (
            f"https://attacker.example{SAVED_PATH}",
            f"http://169.254.169.254{SAVED_PATH}",
            f"http://10.0.0.1{SAVED_PATH}",
            f"http://localhost:8069{SAVED_PATH}",
            None,
        ):
            with self.subTest(url=url), patch.object(requests, "get") as get:
                with self.assertRaises(SavedDocumentRefused):
                    self.read_saved_document(url)
                get.assert_not_called()

    def test_a_redirect_is_never_followed(self):
        self.service.answer(SAVED_PATH, status=302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})

        with self.assertRaises(SavedDocumentRefused):
            self.read_saved_document(f"{PUBLIC_URL}{SAVED_PATH}")

    def test_a_document_over_the_limit_is_refused_by_its_length(self):
        self.service.answer(SAVED_PATH, CONTENT)

        with patch.object(saved_documents, "MAX_SIZE", len(CONTENT) - 1), self.assertRaises(SavedDocumentTooLarge):
            self.read_saved_document(f"{PUBLIC_URL}{SAVED_PATH}")

    def test_a_document_over_the_limit_without_a_length_is_refused_while_it_arrives(self):
        self.service.answer(SAVED_PATH, CONTENT, headers={"Transfer-Encoding": "chunked"})
        received = []

        with patch.object(saved_documents, "MAX_SIZE", 2048), patch.object(saved_documents, "CHUNK_SIZE", 512):
            with self.assertRaises(SavedDocumentTooLarge), saved_document(f"{PUBLIC_URL}{SAVED_PATH}") as chunks:
                received.extend(chunks)

        self.assertLessEqual(sum(map(len, received)), 2048)

    def test_the_whole_fetch_has_a_time_limit(self):
        self.service.answer(SAVED_PATH, CONTENT)

        with patch.object(saved_documents, "TOTAL_SECONDS", -1), self.assertRaises(SavedDocumentUnavailable):
            self.read_saved_document(f"{PUBLIC_URL}{SAVED_PATH}")

    def test_an_editing_service_that_does_not_give_the_document_is_tried_again_later(self):
        self.service.answer(SAVED_PATH, status=500)
        with self.assertRaises(SavedDocumentUnavailable):
            self.read_saved_document(f"{PUBLIC_URL}{SAVED_PATH}")
        for error in (requests.ConnectionError(), requests.Timeout()):
            with self.subTest(error=type(error).__name__), patch.object(requests, "get", side_effect=error):
                with self.assertRaises(SavedDocumentUnavailable):
                    self.read_saved_document(f"{PUBLIC_URL}{SAVED_PATH}")
