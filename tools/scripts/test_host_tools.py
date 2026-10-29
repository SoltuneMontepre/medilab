"""Verify native host invocation and selected endpoint boundaries without application changes."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import host_tools


class HostToolsTests(unittest.TestCase):
    def test_native_invocation_preserves_spaces_unicode_and_child_environment(self):
        result = host_tools.run(
            [
                sys.executable,
                "-c",
                "import json,os,sys;print(json.dumps([sys.argv[1:],os.environ['PROBE']]))",
                "two words",
                "kiểm tra",
            ],
            env={**os.environ, "PROBE": "owned fixture"},
            capture_output=True,
        )
        self.assertEqual(
            json.loads(result.stdout), [["two words", "kiểm tra"], "owned fixture"]
        )

    def test_native_failure_keeps_the_actual_exit_status(self):
        with self.assertRaises(subprocess.CalledProcessError) as error:
            host_tools.run(
                [sys.executable, "-c", "raise SystemExit(17)"], capture_output=True
            )
        self.assertEqual(error.exception.returncode, 17)

    def test_batch_launching_is_explicit_and_rejects_shell_expansion(self):
        with (
            patch.object(host_tools.os, "name", "nt"),
            patch.object(
                host_tools, "executable", return_value=r"C:\Program Files\Node\npx.cmd"
            ),
        ):
            result = host_tools.process_arguments(
                ["npx", "--version"], {"COMSPEC": r"C:\Windows\System32\cmd.exe"}
            )
            self.assertIn('/d /s /v:off /c ""C:\\Program Files', result)
            for value in [
                "value&command",
                "%TOKEN%",
                "!TOKEN!",
                'embedded"quote',
                "line\nbreak",
            ]:
                with self.assertRaises(host_tools.HostError):
                    host_tools.process_arguments(["npx", value])

    @unittest.skipUnless(os.name == "nt", "native Windows batch-launcher contract")
    def test_native_windows_batch_launcher_with_spaces_and_unicode(self):
        with tempfile.TemporaryDirectory(prefix="host tools kiểm tra ") as directory:
            root = Path(directory)
            probe = root / "probe.py"
            probe.write_text(
                "import json,sys; print(json.dumps(sys.argv[1:]))\n", encoding="utf-8"
            )
            launcher = root / "tool.cmd"
            launcher.write_text(
                '@echo off\n@"%MEDILAB_TEST_PYTHON%" "%~dp0probe.py" %*\n',
                encoding="ascii",
            )
            result = host_tools.run(
                [str(launcher), "two words", "kiểm tra"],
                env={**os.environ, "MEDILAB_TEST_PYTHON": sys.executable},
                capture_output=True,
            )
            self.assertEqual(json.loads(result.stdout), ["two words", "kiểm tra"])

    def selected_url(self, values, marker=None, *, strict=False):
        with (
            patch("demo_bootstrap._read_compose_env", return_value=values),
            patch("demo_bootstrap._read_marker", return_value=marker),
            patch("compose_env.project_name", return_value="owned-project"),
        ):
            return host_tools.selected_odoo_url(require_saved_selection=strict)

    def runtime(
        self, *, project="owned-project", port="28169", running=True, owner=None
    ):
        labels = {
            "com.docker.compose.project": project,
            "com.docker.compose.service": "odoo",
        }
        if owner:
            labels["com.medilab.bootstrap.owner"] = owner
        return {
            "Config": {"Labels": labels},
            "State": {"Running": running},
            "NetworkSettings": {
                "Ports": {"8069/tcp": [{"HostPort": port, "HostIp": "0.0.0.0"}]}
            },
        }

    def test_network_requires_saved_worktree_selection_before_engine_or_http(self):
        for values in (
            {},
            {"COMPOSE_PROJECT_NAME": "another-worktree", "MEDILAB_ODOO_PORT": "28169"},
        ):
            with (
                self.subTest(values=values),
                patch("demo_bootstrap._assert_local_engine") as engine,
                patch("local_compose._resolve") as resolve,
            ):
                with self.assertRaises(host_tools.HostError):
                    self.selected_url(values, strict=True)
                engine.assert_not_called()
                resolve.assert_not_called()

    def test_network_checks_running_project_and_published_port(self):
        values = {"COMPOSE_PROJECT_NAME": "owned-project", "MEDILAB_ODOO_PORT": "28169"}
        with (
            patch("demo_bootstrap._assert_local_engine"),
            patch(
                "local_compose._resolve", return_value=("owned-project", None, [], {})
            ),
            patch("demo_bootstrap._inspect", return_value=[self.runtime()]),
        ):
            self.assertEqual(
                self.selected_url(values, strict=True), "http://localhost:28169"
            )
        for runtime in (
            self.runtime(project="another-worktree"),
            self.runtime(port="28170"),
            self.runtime(running=False),
        ):
            with (
                self.subTest(runtime=runtime),
                patch("demo_bootstrap._assert_local_engine"),
                patch(
                    "local_compose._resolve",
                    return_value=("owned-project", None, [], {}),
                ),
                patch("demo_bootstrap._inspect", return_value=[runtime]),
                self.assertRaises(host_tools.HostError),
            ):
                self.selected_url(values, strict=True)

    def test_network_checks_bootstrap_owner_in_addition_to_compose_labels(self):
        values = {"COMPOSE_PROJECT_NAME": "owned-project", "MEDILAB_ODOO_PORT": "28169"}
        saved = {
            "project": "owned-project",
            "status": "completed",
            "owner": "saved-owner",
            "config": values,
        }
        with (
            patch("demo_bootstrap._assert_local_engine"),
            patch(
                "local_compose._resolve", return_value=("owned-project", saved, [], {})
            ),
            patch(
                "demo_bootstrap._inspect",
                return_value=[self.runtime(owner="foreign-owner")],
            ),
            self.assertRaises(host_tools.HostError),
        ):
            self.selected_url(values, saved, strict=True)

    def test_offline_endpoint_selection_has_no_runtime_requirement(self):
        with (
            patch("demo_bootstrap._assert_local_engine") as engine,
            patch("local_compose._resolve") as resolve,
        ):
            self.assertEqual(self.selected_url({}), "http://localhost:8069")
            self.assertEqual(
                self.selected_url(
                    {"MEDILAB_ODOO_PORT": "28169"},
                    {
                        "project": "owned-project",
                        "status": "selected",
                        "config": {"MEDILAB_ODOO_PORT": "28169"},
                    },
                ),
                "http://localhost:28169",
            )
            engine.assert_not_called()
            resolve.assert_not_called()

    def test_published_binding_must_serve_the_selected_loopback_address(self):
        binding = {"HostPort": "28169", "HostIp": "127.0.0.1"}
        self.assertTrue(host_tools.binding_matches(binding, 28169, "127.0.0.1"))
        self.assertFalse(host_tools.binding_matches(binding, 28169, "127.0.0.2"))
        self.assertFalse(
            host_tools.binding_matches(
                {**binding, "HostIp": "192.168.1.2"}, 28169, "localhost"
            )
        )
        self.assertTrue(
            host_tools.binding_matches(
                {**binding, "HostIp": "0.0.0.0"}, 28169, "127.0.0.2"
            )
        )
        self.assertTrue(
            host_tools.binding_matches({**binding, "HostIp": "::"}, 28169, "::1")
        )
        self.assertFalse(
            host_tools.binding_matches({**binding, "HostIp": "::"}, 28169, "127.0.0.1")
        )

    def test_saved_selected_port_and_base_path_are_preserved(self):
        values = {
            "MEDILAB_ODOO_PORT": "28169",
            "MEDILAB_URL": "http://localhost:28169/lab/",
        }
        self.assertEqual(self.selected_url(values), "http://localhost:28169/lab")
        marker = {
            "project": "owned-project",
            "status": "completed",
            "config": {"MEDILAB_ODOO_PORT": "28169"},
        }
        self.assertEqual(
            self.selected_url(values, marker), "http://localhost:28169/lab"
        )
        self.assertEqual(
            self.selected_url(
                {
                    "MEDILAB_ODOO_PORT": "28169",
                    "MEDILAB_URL": "http://127.0.0.2:28169/lab",
                }
            ),
            "http://127.0.0.2:28169/lab",
        )

    def test_endpoint_refuses_foreign_ports_credentials_remote_origins_and_marker_drift(
        self,
    ):
        for url in [
            "http://localhost:8069",
            "http://user:secret@localhost:28169",
            "https://remote.invalid:28169",
            "http://localhost:28169?token=x",
            "http://localhost:28169/#x",
        ]:
            with self.subTest(url=url), self.assertRaises(host_tools.HostError):
                self.selected_url({"MEDILAB_ODOO_PORT": "28169", "MEDILAB_URL": url})
        with self.assertRaises(host_tools.HostError):
            self.selected_url(
                {"MEDILAB_ODOO_PORT": "28169"},
                {
                    "project": "owned-project",
                    "status": "completed",
                    "config": {"MEDILAB_ODOO_PORT": "28170"},
                },
            )


if __name__ == "__main__":
    unittest.main()
