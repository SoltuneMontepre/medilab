"""Safety checks for the literal core-test Task entrypoint."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core_test_guard import CoreTestError, _database_names, _run_directory, prepare


class CoreTestGuardTest(unittest.TestCase):
    def test_app_database_is_never_a_test_database(self):
        with self.assertRaisesRegex(CoreTestError, "application database"):
            _database_names("medilab", "medilab", "1 2")

    def test_app_database_cannot_match_a_shard_database(self):
        with self.assertRaisesRegex(CoreTestError, "application database"):
            _database_names("medilab_test", "medilab_test_1", "1 2")

    def test_test_database_and_shards_are_validated_before_compose(self):
        for database, shards in (
            ("medilab_test;dropdb", "1 2"),
            ("medilab_test", "1;2"),
            ("medilab_test", "1 1"),
        ):
            with (
                self.subTest(database=database, shards=shards),
                self.assertRaises(CoreTestError),
            ):
                _database_names(database, "medilab", shards)

    def test_run_directory_is_derived_from_validated_database(self):
        self.assertEqual(
            _run_directory("medilab_test"), "/var/lib/odoo/medilab_test-run"
        )

    def test_preflight_refuses_existing_database_without_cleanup(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("core_test_guard.MARKERS", Path(directory)),
            patch.dict(
                os.environ,
                {
                    "TEST_DB": "medilab_test",
                    "TEST_RUN_DIR": "/var/lib/odoo/medilab_test-run",
                    "SHARD_NUMBERS": "1 2",
                },
            ),
            patch(
                "core_test_guard._resolve",
                return_value=("medilab-test", None, [], {"MEDILAB_DB_NAME": "medilab"}),
            ),
            patch("core_test_guard._database_exists", return_value=True),
            patch("core_test_guard._compose") as compose,
            self.assertRaisesRegex(CoreTestError, "already exists"),
        ):
            prepare()
        compose.assert_not_called()


if __name__ == "__main__":
    unittest.main()
