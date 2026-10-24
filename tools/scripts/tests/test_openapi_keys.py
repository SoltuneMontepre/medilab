"""test_openapi_keys.py refuses a document that defines a key twice in one mapping, naming the key and its line."""

import contextlib
import io
import unittest
from pathlib import Path

import test_openapi_keys

FIXTURES = Path(__file__).parent / "fixtures"
OPENAPI_DOCUMENT = (
    Path(__file__).parents[3] / "src/core/modules/sol_laboratory/api/openapi.yaml"
)


class TestOpenapiKeys(unittest.TestCase):
    def run_main(self, document):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = test_openapi_keys.main(str(document))
        return code, output.getvalue()

    def test_a_duplicate_schema_is_refused_with_its_key_and_line(self):
        document = FIXTURES / "duplicate_schema.yaml"
        code, output = self.run_main(document)
        self.assertEqual(code, 1)
        self.assertEqual(
            output, f"{document}:12: key Sha256 is already defined on line 8.\n"
        )

    def test_the_same_key_in_different_mappings_is_accepted(self):
        text = "a:\n  name: x\nb:\n  name: y\nitems:\n  - name: x\n  - name: y\n"
        self.assertEqual(test_openapi_keys.duplicate_keys(text), [])

    def test_duplicates_in_nested_mappings_and_sequences_are_found(self):
        text = "a:\n  - b: 1\n    b: 2\nc:\n  d:\n    e: 1\n    e: 2\n"
        self.assertEqual(
            test_openapi_keys.duplicate_keys(text), [("b", 3, 2), ("e", 7, 6)]
        )

    def test_a_document_outside_the_repository_is_refused(self):
        self.assertEqual(self.run_main("../outside.yaml")[0], 2)

    def test_the_laboratory_files_api_document_has_no_duplicate_key(self):
        self.assertEqual(self.run_main(OPENAPI_DOCUMENT), (0, ""))


if __name__ == "__main__":
    unittest.main()
