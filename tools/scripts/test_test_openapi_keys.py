"""test_openapi_keys.py refuses a document that defines a key twice in one mapping, naming the key and its line."""

import contextlib
import io
import unittest
from pathlib import Path

import test_openapi_keys

DUPLICATE_SCHEMA = Path(__file__).parent / "test_openapi_keys_duplicate_schema.yaml"


class TestOpenapiKeys(unittest.TestCase):
    def run_main(self, document):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = test_openapi_keys.main(str(document))
        return code, output.getvalue()

    def test_a_duplicate_schema_is_refused_with_its_key_and_line(self):
        code, output = self.run_main(DUPLICATE_SCHEMA)
        self.assertEqual(code, 1)
        self.assertEqual(output, f"{DUPLICATE_SCHEMA}:12: key Sha256 is already defined on line 8.\n")

    def test_the_same_key_in_different_mappings_is_accepted(self):
        text = "a:\n  name: x\nb:\n  name: y\nitems:\n  - name: x\n  - name: y\n"
        self.assertEqual(test_openapi_keys.duplicate_keys(text), [])

    def test_duplicates_in_nested_mappings_and_sequences_are_found(self):
        text = "a:\n  - b: 1\n    b: 2\nc:\n  d:\n    e: 1\n    e: 2\n"
        self.assertEqual(test_openapi_keys.duplicate_keys(text), [("b", 3, 2), ("e", 7, 6)])

    def test_a_recursive_alias_is_walked_once(self):
        self.assertEqual(test_openapi_keys.duplicate_keys("a: &x [*x]\n"), [])

    def test_a_duplicate_behind_an_alias_is_reported_once(self):
        text = "a: &x\n  b: 1\n  b: 2\nc: *x\n"
        self.assertEqual(test_openapi_keys.duplicate_keys(text), [("b", 3, 2)])

    def test_a_document_outside_the_repository_is_refused(self):
        self.assertEqual(self.run_main("../outside.yaml")[0], 2)


if __name__ == "__main__":
    unittest.main()
