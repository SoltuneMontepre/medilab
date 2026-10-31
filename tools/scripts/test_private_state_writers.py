"""Private journals reject mutable ancestors before reading or publishing state."""

import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import compose_env
import demo_bootstrap as bootstrap
import onlyoffice_state as state
from local_private_paths import ensure_local_directory


class PrivateStateWritersTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.local = ensure_local_directory(self.root, self.root / ".local")
        self.marker = self.local / "demo-bootstrap.json"
        self.journal = self.local / "demo-bootstrap-switch.json"
        self.context = ExitStack()
        self.addCleanup(self.context.close)
        for module in (bootstrap, state):
            self.context.enter_context(patch.object(module, "ROOT", self.root))
        for module in (bootstrap, compose_env):
            self.context.enter_context(patch.object(module, "MARKER", self.marker))
            self.context.enter_context(
                patch.object(module, "SWITCH_JOURNAL", self.journal)
            )
        self.context.enter_context(
            patch.object(state, "DIRECTORY", self.local / "onlyoffice")
        )
        self.context.enter_context(
            patch.object(bootstrap, "SELECTIONS", self.local / "selections")
        )

    @unittest.skipIf(
        os.name == "nt",
        "POSIX mutation permissions; native ACL equivalent has a separate contract",
    )
    def test_private_ancestor_rejects_read_and_write_even_when_leaf_is_absent(self):
        self.local.chmod(0o777)
        try:
            for operation in (
                bootstrap._read_marker,
                lambda: bootstrap._write_marker({"private": "marker"}),
                lambda: bootstrap._saved_selection("medilab-bootstrap-test"),
                lambda: bootstrap._write_switch_journal({}, {}),
                lambda: compose_env.selected_project_name(self.root),
                lambda: state.read_state("medilab-test"),
            ):
                with (
                    self.subTest(operation=operation),
                    self.assertRaises(
                        (bootstrap.BootstrapError, ValueError, state.OnlyofficeError)
                    ),
                ):
                    operation()
            self.assertEqual(list(self.local.iterdir()), [])
            self.assertEqual(self.local.stat().st_mode & 0o777, 0o777)
        finally:
            self.local.chmod(0o700)
        bootstrap._write_marker({"status": "preparing"})
        self.assertEqual(bootstrap._read_marker(), {"status": "preparing"})

    @unittest.skipIf(
        os.name == "nt", "Native links require a separate privilege on Windows"
    )
    def test_predictable_temporary_symlinks_cannot_overwrite_unrelated_files(self):
        victim = self.root / "unrelated.txt"
        victim.write_text("unchanged", encoding="utf-8")
        marker_link = self.marker.with_suffix(".tmp")
        marker_link.symlink_to(victim)
        env = self.root / "infrastructure/.env"
        env.parent.mkdir()
        env.write_text("PRESERVED=value\nCOMPOSE_PROJECT_NAME=old\n", encoding="utf-8")
        env_link = env.with_suffix(".tmp")
        env_link.symlink_to(victim)
        bootstrap._write_marker({"status": "preparing"})
        with patch.object(bootstrap, "COMPOSE_ENV_FILE", env):
            bootstrap._write_compose_env({"COMPOSE_PROJECT_NAME": "new"})
            self.assertEqual(
                env.read_text(), "PRESERVED=value\nCOMPOSE_PROJECT_NAME=new\n"
            )
            bootstrap._remove_compose_env({"COMPOSE_PROJECT_NAME": "new"})
            self.assertEqual(env.read_text(), "PRESERVED=value\n")
        self.assertEqual(victim.read_text(), "unchanged")
        self.assertTrue(marker_link.is_symlink())
        self.assertTrue(env_link.is_symlink())
        self.assertEqual(json.loads(self.marker.read_text()), {"status": "preparing"})
        self.assertFalse(list(self.local.glob(".medilab-*")))
        self.assertFalse(list(env.parent.glob(".medilab-*")))

    def test_journal_exclusive_publish_preserves_existing_transaction_and_cleans_only_own_temp(
        self,
    ):
        bootstrap._write_switch_journal({"owner": "first"}, {"owner": "second"})
        original = self.journal.read_bytes(), self.journal.stat().st_mtime_ns
        with self.assertRaisesRegex(
            bootstrap.BootstrapError, "interrupted project switch"
        ):
            bootstrap._write_switch_journal({}, {})
        self.assertEqual(
            original, (self.journal.read_bytes(), self.journal.stat().st_mtime_ns)
        )
        self.assertFalse(list(self.local.glob(".medilab-*")))

    def test_failed_atomic_publish_preserves_existing_marker_and_removes_only_created_temp(
        self,
    ):
        bootstrap._write_marker({"owner": "original"})
        before = self.marker.read_bytes()
        other = self.local / ".medilab-unrelated"
        other.write_text("unrelated")
        with (
            patch.object(Path, "replace", side_effect=OSError("synthetic failure")),
            self.assertRaises(OSError),
        ):
            bootstrap._write_marker({"owner": "replacement"})
        self.assertEqual(self.marker.read_bytes(), before)
        self.assertEqual(other.read_text(), "unrelated")
        self.assertEqual(list(self.local.glob(".medilab-*")), [other])


if __name__ == "__main__":
    unittest.main()
