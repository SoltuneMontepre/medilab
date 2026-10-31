"""Installation failures never publish metadata and remove only the run's labelled resources."""

import inspect
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import prepare_registry
from registry_export import stable_signature


class TestRegistryFailures(unittest.TestCase):
    def test_signatures_do_not_record_process_addresses(self):
        def first(callback=lambda: None):
            pass

        def second(callback=lambda: None):
            pass

        self.assertEqual(
            stable_signature(inspect.signature(first)),
            stable_signature(inspect.signature(second)),
        )
        self.assertEqual(
            stable_signature(inspect.signature(first)), "(callback=Ellipsis)"
        )

    def test_failed_install_cleans_up_the_owned_database_and_network(self):
        owner = "registry-test-owner"
        commands = []

        def run(*arguments, **options):
            commands.append(arguments)
            if arguments[:3] == ("docker", "image", "inspect"):
                return subprocess.CompletedProcess(arguments, 0, "sha256:probe\n")
            if arguments[:4] == ("docker", "container", "ls", "--all"):
                return subprocess.CompletedProcess(
                    arguments, 0, f"medilab-typecheck-{owner}-odoo\n"
                )
            if len(arguments) > 2 and arguments[2] == "inspect":
                return subprocess.CompletedProcess(
                    arguments,
                    0,
                    json.dumps(
                        [
                            {
                                "Labels": {prepare_registry.OWNER_LABEL: owner},
                                "Config": {
                                    "Labels": {prepare_registry.OWNER_LABEL: owner}
                                },
                            }
                        ]
                    ),
                )
            if (
                "--init" in arguments
                and arguments[-1] != "base"
                and arguments[-1] != "l10n_vn"
            ):
                raise subprocess.CalledProcessError(1, arguments)
            return subprocess.CompletedProcess(arguments, 0, "")

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "registry"
            with (
                patch.object(prepare_registry.uuid, "uuid4") as uuid,
                patch.object(prepare_registry, "verify_core"),
                patch.object(
                    prepare_registry, "fingerprint", return_value={"source": "probe"}
                ),
                patch.object(prepare_registry, "run", side_effect=run),
                patch.object(
                    prepare_registry.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], 0),
                ),
            ):
                uuid.return_value.hex = owner
                with self.assertRaises(subprocess.CalledProcessError):
                    prepare_registry.prepare("probe-image", output)
            self.assertFalse((output / "inputs.json").exists())
            self.assertEqual(
                json.loads((output / "owner.json").read_text())["state"], "cleaned"
            )
        removed = [args[-1] for args in commands if len(args) > 2 and args[2] == "rm"]
        self.assertEqual(
            removed,
            [f"medilab-typecheck-{owner}-{suffix}" for suffix in ("odoo", "db", "net")],
        )


if __name__ == "__main__":
    unittest.main()
