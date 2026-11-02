"""Reject stale inputs, changed output, and publication or lock ownership conflicts."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import artifacts
import prepare_types
import typing_inputs


class TestTypingArtifacts(unittest.TestCase):
    def test_output_hashes_detect_changed_missing_and_added_files(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            source = directory / "model.pyi"
            source.write_text("class Model: ...\n")
            (directory / "pyrightconfig.json").write_text("{}")
            original = artifacts.artifact_hashes(directory)
            marker = {
                "workspace": os.path.normcase(str(directory.resolve())),
                "image": "sha256:probe",
                "artifacts": original,
            }
            (directory / "build.json").write_text(json.dumps(marker))
            with patch.object(artifacts, "require_current"):
                self.assertEqual(artifacts.validate(directory, directory), marker)
                for action in (
                    lambda: source.write_text("class Changed: ...\n"),
                    source.unlink,
                    lambda: (directory / "extra.pyi").write_text("class Added: ...\n"),
                ):
                    action()
                    with self.assertRaisesRegex(ValueError, "missing or changed"):
                        artifacts.validate(directory, directory)

    def test_input_changes_invalidate_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            original = {
                "source": "one",
                "odooRevision": "revision",
                "image": "sha256:probe",
            }
            (directory / "inputs.json").write_text(json.dumps(original))
            with patch.object(typing_inputs, "fingerprint", return_value=original):
                typing_inputs.require_current(directory, directory, "sha256:probe")
            for key in original:
                with (
                    self.subTest(input=key),
                    patch.object(
                        typing_inputs,
                        "fingerprint",
                        return_value=original | {key: "changed"},
                    ),
                    self.assertRaisesRegex(ValueError, "inputs changed"),
                ):
                    typing_inputs.require_current(directory, directory, "sha256:probe")

    def test_lock_is_exclusive_and_removed_only_by_its_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            with (
                prepare_types.preparation_lock(directory),
                self.assertRaisesRegex(RuntimeError, "already locked"),
                prepare_types.preparation_lock(directory),
            ):
                self.fail("A second preparation acquired the lock.")
            self.assertFalse((directory / "prepare.lock").exists())
            with (
                self.assertRaisesRegex(RuntimeError, "changed ownership"),
                prepare_types.preparation_lock(directory),
            ):
                (directory / "prepare.lock").write_text('{"owner":"someone else"}')
            self.assertTrue((directory / "prepare.lock").exists())

    def test_publication_refuses_an_unowned_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target, stage = root / "current", root / "stage"
            target.mkdir()
            stage.mkdir()
            (target / "build.json").write_text(
                json.dumps({"workspace": "elsewhere", "owner": "another"})
            )
            with self.assertRaisesRegex(RuntimeError, "unowned"):
                prepare_types.publish(stage, target, root)
            self.assertTrue(stage.is_dir())
            self.assertTrue(target.is_dir())

    def test_failed_publish_restores_the_previous_owned_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "current"
            target.mkdir()
            (target / "build.json").write_text(
                json.dumps(
                    {"workspace": os.path.normcase(str(root.resolve())), "owner": "one"}
                )
            )
            with self.assertRaises(FileNotFoundError):
                prepare_types.publish(root / "missing", target, root)
            self.assertEqual(
                json.loads((target / "build.json").read_text())["owner"], "one"
            )

    def test_missing_image_is_built_from_the_checkout_without_retagging_other_images(
        self,
    ):
        with (
            patch.object(
                prepare_types,
                "image_id",
                side_effect=[
                    subprocess.CalledProcessError(1, "inspect"),
                    "sha256:probe",
                ],
            ),
            patch.object(prepare_types, "command") as command,
        ):
            root = Path(__file__).resolve().parents[2]
            name, identifier = prepare_types.ensure_image(root, None)
            self.assertEqual(identifier, "sha256:probe")
            self.assertEqual(name, prepare_types.private_image(root))
            self.assertIn(name, command.call_args.args)
            self.assertNotEqual(name, "medilab-odoo:local")


if __name__ == "__main__":
    unittest.main()
