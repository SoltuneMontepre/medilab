"""A fixture generator cannot overwrite an existing file or escape its private worktree directory."""

import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.onlyoffice_integration import runtime_env


class TestRuntimeEnvironment(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.enterContext(patch.object(runtime_env, "ROOT", self.root))

    def test_new_fixture_has_private_permissions(self):
        target = self.root / ".local" / "run" / "settings.env"

        self.assertEqual(runtime_env.write_fixture(target, {"SETTING": "fixture"}), target)

        self.assertEqual(target.read_text(), "SETTING=fixture\n")
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_existing_fixture_is_preserved(self):
        target = self.root / ".local" / "settings.env"
        runtime_env.write_fixture(target, {"SETTING": "original"})

        with self.assertRaises(FileExistsError):
            runtime_env.write_fixture(target, {"SETTING": "replacement"})

        self.assertEqual(target.read_text(), "SETTING=original\n")

    def test_output_outside_the_private_directory_is_refused(self):
        with self.assertRaises(ValueError):
            runtime_env.write_fixture(self.root / "config.env", {"SETTING": "fixture"})
        self.assertFalse((self.root / "config.env").exists())

    def test_symlink_cannot_redirect_fixture_output(self):
        private = self.root / ".local"
        private.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        (private / "redirect").symlink_to(outside, target_is_directory=True)

        with self.assertRaises(ValueError):
            runtime_env.write_fixture(private / "redirect" / "settings.env", {"SETTING": "fixture"})

        self.assertFalse((outside / "settings.env").exists())

    def test_existing_symlink_cannot_create_a_different_private_fixture(self):
        private = self.root / ".local"
        private.mkdir()
        target = private / "other.env"
        alias = private / "settings.env"
        alias.symlink_to(target)

        with self.assertRaises(ValueError):
            runtime_env.write_fixture(alias, {"SETTING": "fixture"})

        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
