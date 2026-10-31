"""An unsaved or absent record must not silently become a database identifier."""

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

PATH = (
    Path(__file__).resolve().parents[2]
    / "src/core/modules/sol_laboratory/services/record_id.py"
)
SPEC = importlib.util.spec_from_file_location("record_id_contract", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TestRecordId(unittest.TestCase):
    def test_database_identifier_is_preserved(self):
        self.assertEqual(MODULE.persisted_id(SimpleNamespace(id=7)), 7)

    def test_non_database_identifiers_are_rejected(self):
        for value in (False, True, 0, -1, "7", None, object()):
            record = SimpleNamespace(id=value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                MODULE.persisted_id(record)

    def test_a_collection_cannot_hide_an_unsaved_record(self):
        records = [SimpleNamespace(id=7), SimpleNamespace(id=False)]
        with self.assertRaises(ValueError):
            MODULE.persisted_ids(records)


if __name__ == "__main__":
    unittest.main()
