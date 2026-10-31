"""Shared local-state permissions across independent developer tasks."""

import contextlib
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core_test_guard
import test_openapi


@unittest.skipIf(os.name == "nt", "POSIX umask contract")
class LocalStateCreatorsTest(unittest.TestCase):
    def test_core_marker_cannot_make_later_setup_refuse_the_checkout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            marker = root / ".local/core-test-runs/owned.json"
            state = {"names": ["owned_test"], "run_directory": "/owned/test-run"}
            previous = os.umask(0o002)
            try:
                with (
                    patch.object(core_test_guard, "ROOT", root),
                    patch.object(
                        core_test_guard,
                        "_selection",
                        return_value=(None, marker, state),
                    ),
                    patch.object(
                        core_test_guard, "_database_exists", return_value=False
                    ),
                    patch.object(
                        core_test_guard, "_run_directory_exists", return_value=False
                    ),
                ):
                    core_test_guard.prepare()
            finally:
                os.umask(previous)
            self.assertTrue(marker.is_file())
            for path in (marker.parent, root / ".local"):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)

    def test_openapi_comparison_keeps_its_local_directories_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            document = root / "api.yaml"
            source = "info:\n  version: 1.0.0\n"
            document.write_text(source, encoding="utf-8")
            previous = os.umask(0o002)
            try:
                with (
                    contextlib.chdir(root),
                    patch.object(test_openapi, "WORK_DIR", root / ".local/openapi"),
                    patch.object(
                        test_openapi.subprocess,
                        "run",
                        side_effect=[
                            subprocess.CompletedProcess([], 0, source),
                            subprocess.CompletedProcess([], 0),
                        ],
                    ),
                ):
                    self.assertEqual(
                        test_openapi.main(str(document), "owned-image", "base"), 0
                    )
            finally:
                os.umask(previous)
            for path in (root / ".local", root / ".local/openapi"):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)


if __name__ == "__main__":
    unittest.main()
