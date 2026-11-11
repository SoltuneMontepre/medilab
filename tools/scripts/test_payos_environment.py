"""Check optional PayOS environment forwarding without using credentials or containers."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from demo_bootstrap import _compose_environment
from local_compose import _resolve

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "tools/infrastructure/docker-compose.yml"
PAYOS_KEYS = ("PAYOS_CLIENT_ID", "PAYOS_API_KEY", "PAYOS_CHECKSUM_KEY")


class PayosEnvironmentTest(unittest.TestCase):
    def _odoo_environment(self, configured):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / "empty.env"
            env_file.write_text("", encoding="utf-8")
            environment = {
                key: value
                for key, value in os.environ.items()
                if not key.startswith("PAYOS_")
            }
            if configured:
                environment.update({key: "test-only" for key in PAYOS_KEYS})
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "--env-file",
                    str(env_file),
                    "-f",
                    str(COMPOSE),
                    "config",
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(result.stdout)["services"]["odoo"]["environment"]

    def test_compose_forwards_all_explicit_payos_variables(self):
        environment = self._odoo_environment(configured=True)
        self.assertTrue(all(key in environment for key in PAYOS_KEYS))

    def test_compose_omits_unconfigured_payos_variables(self):
        environment = self._odoo_environment(configured=False)
        self.assertTrue(all(environment.get(key) is None for key in PAYOS_KEYS))

    def test_private_demo_environment_discards_host_payos_variables(self):
        with patch.dict(os.environ, {key: "test-only" for key in PAYOS_KEYS}):
            environment = _compose_environment("medilab-bootstrap-example", "owner")
        self.assertTrue(all(key not in environment for key in PAYOS_KEYS))
        self.assertEqual(environment.get("COMPOSE_DISABLE_ENV_FILE"), "1")

    def test_private_demo_ignores_secret_values_in_compose_dotenv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "".join(f"{key}=test-only\n" for key in PAYOS_KEYS),
                encoding="utf-8",
            )
            (root / "compose.yml").write_text(
                "services:\n  probe:\n    image: hello-world\n    environment:\n"
                + "".join(f"      {key}:\n" for key in PAYOS_KEYS),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    "compose.yml",
                    "config",
                    "--format",
                    "json",
                ],
                cwd=root,
                env=_compose_environment("medilab-bootstrap-example", "owner"),
                capture_output=True,
                text=True,
                check=True,
            )
        environment = json.loads(result.stdout)["services"]["probe"]["environment"]
        self.assertTrue(all(environment.get(key) is None for key in PAYOS_KEYS))

    def test_legacy_compose_receives_explicit_host_variables(self):
        with (
            patch.dict(os.environ, {key: "test-only" for key in PAYOS_KEYS}),
            patch("local_compose.project_name", return_value="medilab-local"),
            patch("local_compose._read_marker", return_value=None),
            patch(
                "local_compose._resources",
                return_value={"containers": [], "networks": [], "volumes": []},
            ),
        ):
            _project, _marker, _files, environment = _resolve("up")
        self.assertTrue(all(key in environment for key in PAYOS_KEYS))


if __name__ == "__main__":
    unittest.main()
