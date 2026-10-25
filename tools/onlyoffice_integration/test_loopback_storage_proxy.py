"""Only origin-relative object paths reach the fixed Garage fixture."""

import unittest

from tools.onlyoffice_integration.loopback_storage_proxy import storage_path


class TestStoragePath(unittest.TestCase):
    def test_signed_object_query_is_preserved(self):
        value = "/laboratory-files/report.docx?signature=fixture"
        self.assertEqual(storage_path(value), value)
        custom = "/laboratory-files-integration-page/report.docx?signature=fixture"
        self.assertEqual(storage_path(custom), custom)

    def test_only_owned_bucket_objects_are_exposed(self):
        for value in (
            "/",
            "/other-bucket/key",
            "/laboratory-files/../admin",
            "/laboratory-files/%2e%2e/admin",
            "/laboratory-files/a%2fb",
            "/laboratory-files/a%5cb",
            "/laboratory-files/a%0ab",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                storage_path(value)

    def test_absolute_targets_and_header_injection_are_refused(self):
        for value in (
            "https://other.example/file",
            "//other.example/file",
            "/\\other.example/file",
            "/a\r\nHost:x",
            "",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                storage_path(value)


if __name__ == "__main__":
    unittest.main()
