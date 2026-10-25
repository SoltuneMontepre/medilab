"""Only origin-relative object paths reach the fixed Garage fixture."""

import unittest

from tools.onlyoffice_integration.loopback_storage_proxy import storage_path


class TestStoragePath(unittest.TestCase):
    def test_signed_object_query_is_preserved(self):
        self.assertEqual(storage_path("/bucket/report.docx?signature=fixture"), "/bucket/report.docx?signature=fixture")

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
