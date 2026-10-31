"""Exercise first-use selection, ordering, refusal and secret isolation of root setup."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import local_setup


def marker(status="selected"):
    return {
        "project": "medilab-bootstrap-test",
        "owner": "owned",
        "status": status,
        "lifecycle_version": 2,
        "config": {
            "COMPOSE_PROJECT_NAME": "medilab-bootstrap-test",
            "MEDILAB_ODOO_PORT": "28169",
        },
    }


class LocalSetupTests(unittest.TestCase):
    def test_compose_version_rejects_unbounded_numeric_components(self):
        for value in ("9" * 100000, "1." + "9" * 100000, "1.2." + "9" * 100000):
            with (
                self.subTest(length=len(value)),
                self.assertRaises(local_setup.HostError),
            ):
                local_setup.check_compose_version(value)

    def test_old_docker_server_is_refused_before_selection_or_mutation(self):
        document = {
            "ServerVersion": "27.5.1",
            "OSType": "linux",
            "Architecture": "amd64",
            "NCPU": 8,
            "MemTotal": 16 * 1024**3,
        }

        def invoke(argv, **_kwargs):
            output = (
                "v24.22.1" if argv == ["node", "--version"] else json.dumps(document)
            )
            return subprocess.CompletedProcess(argv, 0, output, "")

        with (
            patch.object(local_setup, "executable"),
            patch.object(local_setup, "run", side_effect=invoke),
            patch.object(local_setup.bootstrap, "_assert_local_engine"),
            patch.object(local_setup, "classify") as classify,
            patch.object(local_setup, "prepare") as prepare,
            self.assertRaisesRegex(local_setup.HostError, "server 28"),
        ):
            local_setup.setup()
        classify.assert_not_called()
        prepare.assert_not_called()

    def test_node_prerequisite_follows_the_locked_vite_engine_range(self):
        for version in ("v20.19.0", "v20.20.1", "v22.12.0", "v23.0.0", "v24.22.1"):
            local_setup.check_node_version(version)
        for version in ("v20.18.0", "v21.7.0", "v22.11.0", "unknown"):
            with (
                self.subTest(version=version),
                self.assertRaises(local_setup.HostError),
            ):
                local_setup.check_node_version(version)

    def test_remote_podman_is_refused_before_selection_or_mutation(self):
        document = {
            "host": {
                "os": "linux",
                "arch": "amd64",
                "cpus": 16,
                "memTotal": 16 * 1024**3,
                "serviceIsRemote": True,
            }
        }

        def invoke(argv, **_kwargs):
            if argv == ["node", "--version"]:
                output = "v24.22.1"
            elif argv[:2] == ["docker", "info"]:
                output = json.dumps(document)
            elif argv == ["docker", "--version"]:
                output = "podman version 6.1.4"
            elif argv == ["docker", "context", "show"]:
                return subprocess.CompletedProcess(argv, 1, "", "")
            else:
                output = "5.6.1"
            return subprocess.CompletedProcess(argv, 0, output, "")

        for environment in (
            {},
            {"DOCKER_HOST": "unix:///run/local.sock"},
            {"CONTAINER_HOST": "ssh://remote.invalid/run/engine"},
            {"CONTAINER_CONNECTION": "remote-selection"},
        ):
            with (
                self.subTest(environment=environment),
                patch.dict(os.environ, environment, clear=True),
                patch.object(local_setup, "executable"),
                patch.object(local_setup, "run", side_effect=invoke),
                patch.object(local_setup.bootstrap, "_run", side_effect=invoke),
                patch.object(local_setup, "classify") as classify,
                patch.object(local_setup, "prepare") as prepare,
            ):
                with self.assertRaises(
                    (local_setup.HostError, local_setup.bootstrap.BootstrapError)
                ):
                    local_setup.setup()
                classify.assert_not_called()
                prepare.assert_not_called()

    def test_doctor_children_exclude_application_credentials(self):
        with patch.dict(
            os.environ,
            {
                "PAYOS_API_KEY": "fake-private-value",
                "DOPPLER_TOKEN": "fake-private-value",
                "RUSTUP_TOOLCHAIN": "existing",
            },
        ):
            environment = local_setup.host_environment()
        self.assertNotIn("PAYOS_API_KEY", environment)
        self.assertNotIn("DOPPLER_TOKEN", environment)
        self.assertEqual(environment["RUSTUP_TOOLCHAIN"], "existing")

    def test_engine_normalization_supports_docker_and_native_podman(self):
        for document in [
            {
                "OSType": "linux",
                "Architecture": "amd64",
                "NCPU": 8,
                "MemTotal": 12 * 1024**3,
            },
            {
                "host": {
                    "os": "linux",
                    "arch": "amd64",
                    "cpus": 8,
                    "memTotal": 12 * 1024**3,
                }
            },
        ]:
            local_setup.check_engine_resources(local_setup.engine_information(document))
        for changed in [
            {"os": "windows"},
            {"architecture": "arm64"},
            {"memory": 4 * 1024**3},
            {"cpus": 2},
        ]:
            values = {
                "os": "linux",
                "architecture": "amd64",
                "cpus": 8,
                "memory": 12 * 1024**3,
                **changed,
            }
            with (
                self.subTest(changed=changed),
                self.assertRaises(local_setup.HostError),
            ):
                local_setup.check_engine_resources(values)

    def test_compose_required_feature_version_is_checked(self):
        for version in ["2.24.4", "v2.39.0", "5.6.1"]:
            local_setup.check_compose_version(version)
        for version in ["2.24.3", "unavailable"]:
            with self.assertRaises(local_setup.HostError):
                local_setup.check_compose_version(version)

    def test_empty_checkout_selects_existing_guarded_bootstrap_once(self):
        with (
            patch.object(
                local_setup, "project_name", return_value="ordinary-candidate"
            ),
            patch.object(
                local_setup.bootstrap, "_read_marker", side_effect=[None, marker()]
            ),
            patch.object(local_setup.bootstrap, "check_normal_setup"),
            patch.object(
                local_setup.bootstrap,
                "_resources",
                return_value={"containers": [], "volumes": [], "networks": []},
            ),
            patch.object(local_setup.bootstrap, "select") as select,
        ):
            mode, selected = local_setup.classify()
        self.assertEqual(mode, "fresh")
        self.assertEqual(selected["owner"], "owned")
        select.assert_called_once_with(local_setup.fresh_project())

    def test_existing_ordinary_resources_are_not_adopted_or_reseeded(self):
        with (
            patch.object(local_setup, "project_name", return_value="ordinary"),
            patch.object(local_setup.bootstrap, "_read_marker", return_value=None),
            patch.object(local_setup.bootstrap, "check_normal_setup"),
            patch.object(
                local_setup.bootstrap, "_resources", return_value={"containers": [{}]}
            ),
            patch.object(local_setup.bootstrap, "select") as select,
        ):
            self.assertEqual(local_setup.classify(), ("ordinary", None))
        select.assert_not_called()

    def test_failed_marker_retains_existing_refusal_before_any_work(self):
        with (
            patch.object(local_setup, "project_name", return_value=marker()["project"]),
            patch.object(
                local_setup.bootstrap, "_read_marker", return_value=marker("failed")
            ),
            patch.object(local_setup.bootstrap, "select") as select,
            self.assertRaises(local_setup.bootstrap.BootstrapError),
        ):
            local_setup.classify()
        select.assert_not_called()

    def test_fresh_children_have_no_inherited_application_credentials_or_private_dotenv(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            dotenv = Path(directory) / "empty.env"
            dotenv.write_text("", encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "DOPPLER_TOKEN": "secret",
                    "PAYOS_API_KEY": "secret",
                    "ONLYOFFICE_JWT_SECRET": "secret",
                    "RUSTUP_TOOLCHAIN": "existing-toolchain",
                    "CONTAINER_HOST": "unix:///run/owned-podman.sock",
                    "SSL_CERT_FILE": "owned-public-ca.pem",
                    "PROGRAMFILES": r"D:\Program Files",
                    "PROGRAMFILES(X86)": r"D:\Program Files (x86)",
                    "PROGRAMW6432": r"D:\Program Files",
                    "CARGO_BUILD_JOBS": "2",
                },
            ):
                environment = local_setup.fresh_environment(marker(), dotenv)
            for key in ["DOPPLER_TOKEN", "PAYOS_API_KEY", "ONLYOFFICE_JWT_SECRET"]:
                self.assertNotIn(key, environment)
            self.assertEqual(environment["MEDILAB_SETUP_DOTENV"], str(dotenv))
            self.assertEqual(environment["RUSTUP_TOOLCHAIN"], "existing-toolchain")
            self.assertEqual(
                environment["CONTAINER_HOST"], "unix:///run/owned-podman.sock"
            )
            self.assertEqual(environment["SSL_CERT_FILE"], "owned-public-ca.pem")
            self.assertEqual(
                environment["PROGRAMFILES(X86)"], r"D:\Program Files (x86)"
            )
            self.assertEqual(environment["PROGRAMW6432"], r"D:\Program Files")
            self.assertEqual(environment["CARGO_BUILD_JOBS"], "2")
            calls = []
            with (
                patch.object(
                    local_setup,
                    "run",
                    side_effect=lambda argv, **kwargs: calls.append((argv, kwargs)),
                ),
                patch.object(local_setup.bootstrap, "check_normal_setup") as normal,
            ):
                local_setup.prepare("fresh", marker(), environment, "sol_laboratory")
            normal.assert_not_called()
            self.assertEqual(
                [argv[1:] for argv, _ in calls],
                [
                    ["dev:setup"],
                    ["ai:setup"],
                    ["tools/scripts/demo_bootstrap.py", "setup"],
                    ["tools/scripts/sync.py", "verify"],
                    ["tools/scripts/onlyoffice.py", "setup"],
                    ["tools/scripts/sync.py", "setup"],
                    ["tools/scripts/onlyoffice.py", "verify"],
                    ["tools/scripts/sync.py", "verify"],
                ],
            )
            self.assertTrue(all(options["env"] is environment for _, options in calls))

    def test_ordinary_setup_recovers_addon_then_retains_auth_tooling_and_module_upgrade_order(
        self,
    ):
        calls = []
        with (
            patch.object(
                local_setup,
                "run",
                side_effect=lambda argv, **kwargs: calls.append(argv[1:]),
            ),
            patch.object(local_setup, "executable"),
            patch.object(local_setup.bootstrap, "check_normal_setup") as normal,
        ):
            local_setup.prepare("ordinary", None, {}, "sol_laboratory")
        normal.assert_called_once()
        self.assertEqual(
            calls[:6],
            [
                ["tools/scripts/onlyoffice.py", "recover-registration"],
                ["tools/scripts/onlyoffice.py", "guard-existing"],
                ["doppler"],
                ["dev:setup"],
                ["ai:setup"],
                ["upgrade", "MODULES=sol_laboratory"],
            ],
        )

    def test_existing_editor_guard_failure_prevents_authentication_tooling_and_upgrade(
        self,
    ):
        calls = []

        def invoke(argv, **_kwargs):
            calls.append(argv[1:])
            if argv[-2:] == ["tools/scripts/onlyoffice.py", "guard-existing"]:
                raise subprocess.CalledProcessError(29, argv)

        with (
            patch.object(local_setup, "run", side_effect=invoke),
            patch.object(local_setup, "executable"),
            patch.object(local_setup.bootstrap, "check_normal_setup"),
            self.assertRaises(subprocess.CalledProcessError) as error,
        ):
            local_setup.prepare(
                "ordinary",
                None,
                {"ONLYOFFICE_JWT_SECRET": "existing-private-value"},
                "all",
            )
        self.assertEqual(error.exception.returncode, 29)
        self.assertEqual(
            calls,
            [
                ["tools/scripts/onlyoffice.py", "recover-registration"],
                ["tools/scripts/onlyoffice.py", "guard-existing"],
            ],
        )

    def test_required_component_failure_stops_later_setup_and_retains_exit_status(self):
        calls = []
        selected = marker()

        def invoke(argv, **_kwargs):
            calls.append(argv)
            if argv[-2:] == ["tools/scripts/onlyoffice.py", "setup"]:
                raise subprocess.CalledProcessError(19, argv)

        with (
            patch.object(local_setup, "run", side_effect=invoke),
            self.assertRaises(subprocess.CalledProcessError) as error,
        ):
            local_setup.prepare("fresh", selected, {}, "all")
        self.assertEqual(error.exception.returncode, 19)
        self.assertFalse(
            any(argv[-2:] == ["tools/scripts/sync.py", "setup"] for argv in calls)
        )

    def test_base_only_backend_failure_prevents_addon_initialization(self):
        calls = []
        selected = marker()

        def invoke(argv, **_kwargs):
            calls.append(argv)
            if argv[-2:] == ["tools/scripts/sync.py", "verify"]:
                raise subprocess.CalledProcessError(21, argv)

        with (
            patch.object(local_setup, "run", side_effect=invoke),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            local_setup.prepare("fresh", selected, {}, "all")
        self.assertFalse(any("tools/scripts/onlyoffice.py" in argv for argv in calls))

    def test_completed_fresh_recovery_refreshes_config_without_changing_ownership_or_authenticating(
        self,
    ):
        saved = marker("completed")
        updated = {**saved, "config": {**saved["config"], "ONLYOFFICE_PORT": "29843"}}
        calls = []
        with (
            patch.object(
                local_setup,
                "run",
                side_effect=lambda argv, **kwargs: calls.append((argv, kwargs)),
            ),
            patch.object(local_setup.bootstrap, "check_normal_setup"),
            patch.object(local_setup.bootstrap, "_read_marker", return_value=updated),
        ):
            local_setup.prepare(
                "completed-fresh",
                saved,
                {"MEDILAB_SETUP_DOTENV": "owned-empty.env"},
                "all",
            )
        self.assertEqual(
            calls[0][0][-2:], ["tools/scripts/onlyoffice.py", "recover-registration"]
        )
        self.assertFalse(any(argv == ["task", "doppler"] for argv, _ in calls))
        self.assertEqual(calls[1][1]["env"]["ONLYOFFICE_PORT"], "29843")

    def test_corrupted_empty_marker_cannot_be_treated_as_an_empty_worktree(self):
        with (
            patch.object(local_setup, "project_name", return_value="candidate"),
            patch.object(local_setup.bootstrap, "_read_marker", return_value={}),
            patch.object(local_setup.bootstrap, "select") as select,
            self.assertRaises(local_setup.HostError),
        ):
            local_setup.classify()
        select.assert_not_called()

    def test_missing_prerequisite_prevents_selection_or_authentication(self):
        with (
            patch.object(
                local_setup,
                "doctor",
                side_effect=local_setup.HostError("bun was not found"),
            ),
            patch.object(local_setup, "classify") as classify,
            patch.object(local_setup, "prepare") as prepare,
            self.assertRaises(local_setup.HostError),
        ):
            local_setup.setup()
        classify.assert_not_called()
        prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
