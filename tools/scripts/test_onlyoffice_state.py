"""State, registration and ownership tests use disposable directories and mocked engine operations."""

import base64
import copy
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import ExitStack, contextmanager, nullcontext, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import onlyoffice
import onlyoffice_state as state
from local_private_paths import ensure_local_directory


class OnlyofficeStateTest(unittest.TestCase):
    def test_core_environment_reentry_uses_controller_script_and_propagates_exit_status(
        self,
    ):
        result = subprocess.CompletedProcess([], 17)
        with (
            patch.object(onlyoffice, "ROOT", self.root),
            patch.object(Path, "is_file", return_value=True),
            patch.object(onlyoffice.subprocess, "run", return_value=result) as run,
            self.assertRaises(SystemExit) as raised,
        ):
            onlyoffice.onlyoffice_commands.use_core_environment(onlyoffice, "verify")
        self.assertEqual(raised.exception.code, 17)
        executable = (
            self.root
            / "src/core/.venv"
            / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        run.assert_called_once_with(
            [str(executable), str(Path(onlyoffice.__file__).resolve()), "verify"],
            cwd=self.root,
            check=False,
        )

    def test_dotenv_comment_scan_preserves_hashes_and_quoted_values(self):
        cases = (
            ("value" + " " * 100000 + "# comment", "value"),
            ("value" + " " * 100000 + "suffix", "value" + " " * 100000 + "suffix"),
            ("value#literal", "value#literal"),
            ("#literal", "#literal"),
            ('"value # literal" # comment', "value # literal"),
            ("value\u2003# comment", "value"),
        )
        for raw, expected in cases:
            with self.subTest(length=len(raw)):
                self.assertEqual(state.dotenv_value(raw), expected)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.patches = [
            patch.object(state, "ROOT", self.root),
            patch.object(state, "DIRECTORY", self.root / ".local/onlyoffice"),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def generated_state(self):
        with (
            patch.object(onlyoffice, "ROOT", self.root),
            patch.object(onlyoffice.bootstrap, "_published_ports", return_value=set()),
            patch.object(onlyoffice.bootstrap, "_read_compose_env", return_value={}),
            patch.object(onlyoffice, "port_available", return_value=True),
        ):
            return onlyoffice.new_state("medilab-test", None, "local")

    def test_validated_port_accepts_decimal_boundaries_without_coercing_other_types(
        self,
    ):
        for value, expected in (
            ("1", 1),
            ("65535", 65535),
            (1, 1),
            (65535, 65535),
            ("00080", 80),
        ):
            with self.subTest(value=value):
                self.assertEqual(state.validated_port(value), expected)
        for value in (
            True,
            False,
            None,
            [],
            {},
            1.0,
            0,
            65536,
            -1,
            "",
            "0",
            "65536",
            "80@external.invalid",
            "+80",
            " 80",
            "８０",
            "8\n0",
            "9" * 5000,
        ):
            with (
                self.subTest(value_type=type(value).__name__),
                self.assertRaises(state.OnlyofficeError),
            ):
                state.validated_port(value)

    def test_state_loader_accepts_actual_generator_lifecycle_and_preserves_bytes(self):
        addon = self.generated_state()
        directory = state.state_directory(addon["project"])
        ensure_local_directory(self.root, directory)
        state.protect(directory)
        for changes in (
            {},
            {"provider": "podman", "registered": True},
            {
                "provider": "podman",
                "registered": True,
                "status": "completed",
                "material": {
                    name: "a" * 64
                    for name in ("jwt", "tls/public/ca.crt", "tls/server/tls.crt")
                },
            },
        ):
            with self.subTest(status=changes.get("status", "preparing")):
                current = {**addon, **changes}
                file = directory / "state.json"
                state.atomic_json(file, current)
                original = file.read_bytes(), file.stat().st_mtime_ns
                self.assertEqual(
                    state.read_state(addon["project"], engine="local"), current
                )
                self.assertEqual(original, (file.read_bytes(), file.stat().st_mtime_ns))

    def test_malformed_owned_state_is_rejected_before_engine_or_state_mutation_and_can_be_restored(
        self,
    ):
        addon = self.generated_state()
        directory = state.state_directory(addon["project"])
        ensure_local_directory(self.root, directory)
        state.protect(directory)
        file = directory / "state.json"
        broken = [
            None,
            [],
            {**addon, "format": True},
            {**addon, "config": []},
            {**addon, "config": {}},
            {
                **addon,
                "config": {**addon["config"], "DOCKER_HOST": "ssh://external.invalid"},
            },
            {**addon, "owner": 123},
            {**addon, "status": []},
            {**addon, "status": "unknown"},
            {**addon, "provider": "unknown"},
            {**addon, "status": "completed"},
            {**addon, "registered": "true"},
            {**addon, "material": []},
            {**addon, "material": {"jwt": "a" * 64}},
        ]
        for value in (
            "--driver=untrusted",
            "../other-volume",
            "volume\nextra",
            "another-owner-volume",
        ):
            broken.append(
                {**addon, "config": {**addon["config"], state.VOLUME_KEYS[0]: value}}
            )
        for value in (True, 29843, "80@external.invalid", "65536", "８０"):
            broken.append(
                {
                    **addon,
                    "config": {**addon["config"], "MEDILAB_ONLYOFFICE_PORT": value},
                }
            )
        for value in (True, "18080", 0, 65536):
            broken.append({**addon, "http_port": value})
        for index, value in enumerate(broken):
            with self.subTest(case=index):
                state.atomic_json(file, value)
                original = file.read_bytes(), file.stat().st_mtime_ns
                with (
                    patch.object(
                        onlyoffice,
                        "selection",
                        return_value=(addon["project"], None, "local", {}),
                    ),
                    patch.object(onlyoffice.bootstrap, "_resources") as resources,
                    patch.object(onlyoffice, "run") as run,
                    patch.object(onlyoffice, "save") as save,
                    self.assertRaises(state.OnlyofficeError),
                ):
                    onlyoffice.setup()
                resources.assert_not_called()
                run.assert_not_called()
                save.assert_not_called()
                self.assertEqual(original, (file.read_bytes(), file.stat().st_mtime_ns))
                state.atomic_json(file, addon)
                self.assertEqual(
                    state.read_state(addon["project"], engine="local"), addon
                )

    def test_foreign_configured_paths_are_rejected_without_filesystem_probes(self):
        for key in ("ONLYOFFICE_TLS_DIR", "ONLYOFFICE_CA_DIR"):
            with (
                self.subTest(key=key),
                patch.object(
                    state,
                    "checked_path",
                    side_effect=AssertionError("Foreign path must not be inspected"),
                ) as checked,
                self.assertRaises(state.OnlyofficeError),
            ):
                state.assert_configuration_matches(
                    {key: str(self.root / "foreign")}, {key: str(self.root / "owned")}
                )
            checked.assert_not_called()

    def test_equivalent_lexical_paths_probe_only_the_expected_owned_path(self):
        expected = self.root / "owned/tls/server"
        with patch.object(state, "checked_path", return_value=expected) as checked:
            state.assert_configuration_matches(
                {"ONLYOFFICE_TLS_DIR": str(self.root / "owned/tls/unused/../server")},
                {"ONLYOFFICE_TLS_DIR": str(expected)},
            )
        checked.assert_called_once_with(expected)

    def test_optional_identity_is_all_or_none_and_old_four_volume_config_survives(self):
        self.assertEqual(
            state.optional_volume_names({"MEDILAB_DB_VOLUME": "db"}), set()
        )
        config = dict(
            zip(state.CONFIG_KEYS, ("lib", "data", "fonts", "29843"), strict=True)
        )
        self.assertEqual(state.optional_volume_names(config), {"lib", "data", "fonts"})
        for key in state.CONFIG_KEYS:
            broken = dict(config)
            broken.pop(key)
            with self.subTest(key=key), self.assertRaises(state.OnlyofficeError):
                state.optional_volume_names(broken)
        self.assertEqual(state.missing_core_volumes(config, ["db", "data"]), ["db"])

    def test_status_lookup_creates_nothing_and_generation_paths_are_separate(self):
        self.assertIsNone(state.read_state("medilab-test"))
        self.assertFalse((self.root / ".local").exists())
        self.assertNotEqual(
            state.state_directory("medilab-test", "first"),
            state.state_directory("medilab-test", "second"),
        )
        with self.assertRaises(state.OnlyofficeError):
            state.state_directory("../outside")

    @unittest.skipIf(
        os.name == "nt", "POSIX modes; native Windows ACL contracts run separately"
    )
    def test_exposed_private_state_and_symlink_paths_are_refused(self):
        directory = state.state_directory("medilab-test")
        directory.mkdir(parents=True, mode=0o700)
        file = directory / "state.json"
        file.write_text("{}")
        file.chmod(0o644)
        with self.assertRaises(state.OnlyofficeError):
            state.read_state("medilab-test")
        linked = self.root / "linked"
        linked.symlink_to(directory, target_is_directory=True)
        with self.assertRaises(state.OnlyofficeError):
            state.checked_path(linked / "child")

    def test_registration_recovers_both_write_interruptions_without_losing_base_keys(
        self,
    ):
        for changed in ("neither", "marker", "environment", "both"):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as folder:
                directory = Path(folder)
                addon = {
                    "format": 1,
                    "project": "medilab-test",
                    "owner": "a" * 32,
                    "base_owner": "base",
                    "engine": "local",
                    "config": dict(
                        zip(
                            state.CONFIG_KEYS,
                            ("lib", "data", "fonts", "29843"),
                            strict=True,
                        )
                    ),
                }
                before = {"MEDILAB_DB_VOLUME": "db", "MEDILAB_APP_VOLUME": "app"}
                marker = {
                    "config": {
                        **before,
                        **(addon["config"] if changed in {"marker", "both"} else {}),
                    }
                }
                environment = {
                    **before,
                    **(addon["config"] if changed in {"environment", "both"} else {}),
                }
                journal = {
                    "format": 1,
                    "project": addon["project"],
                    "owner": addon["owner"],
                    "base_owner": "base",
                    "engine": "local",
                    "old": {key: None for key in state.CONFIG_KEYS},
                    "new": addon["config"],
                    "base_config": before,
                    "phase": "prepared",
                }
                state.atomic_json(directory / "registration.json", journal)
                with (
                    patch.object(onlyoffice, "state_directory", return_value=directory),
                    patch.object(
                        onlyoffice.bootstrap,
                        "_read_compose_env",
                        side_effect=lambda environment=environment: dict(environment),
                    ),
                    patch.object(
                        onlyoffice.bootstrap,
                        "_write_compose_env",
                        side_effect=environment.update,
                    ),
                    patch.object(onlyoffice.bootstrap, "_write_marker"),
                    patch.object(onlyoffice, "save"),
                ):
                    onlyoffice.recover_registration(addon, marker)
                    self.assertEqual(marker["config"], {**before, **addon["config"]})
                    self.assertEqual(environment, {**before, **addon["config"]})
                    self.assertTrue(addon["registered"])
                    self.assertFalse((directory / "registration.json").exists())

    def test_foreign_registration_change_is_refused_before_any_write(self):
        directory = state.state_directory("medilab-test")
        ensure_local_directory(self.root, directory)
        addon = {
            "project": "medilab-test",
            "owner": "a" * 32,
            "engine": "local",
            "base_owner": None,
            "config": dict(
                zip(state.CONFIG_KEYS, ("lib", "data", "fonts", "29843"), strict=True)
            ),
        }
        state.atomic_json(
            directory / "registration.json",
            {
                **addon,
                "format": 1,
                "old": {key: None for key in state.CONFIG_KEYS},
                "new": addon["config"],
                "base_config": None,
            },
        )
        with (
            patch.object(onlyoffice, "state_directory", return_value=directory),
            patch.object(
                onlyoffice.bootstrap,
                "_read_compose_env",
                return_value={"MEDILAB_ONLYOFFICE_PORT": "unexpected"},
            ),
            patch.object(onlyoffice.bootstrap, "_write_compose_env") as write,
        ):
            with self.assertRaises(state.OnlyofficeError):
                onlyoffice.recover_registration(addon, None)
            write.assert_not_called()

    def test_ordinary_owner_never_claims_bootstrap_label(self):
        ordinary = {"owner": "a" * 32, "project": "medilab-test", "base_owner": None}
        self.assertFalse(
            any(
                "com.medilab.bootstrap.owner" in item
                for item in onlyoffice.labels(ordinary)
            )
        )
        self.assertIn(
            "com.medilab.bootstrap.owner=base",
            onlyoffice.labels({**ordinary, "base_owner": "base"}),
        )

    def test_readonly_base_operations_survive_corrupt_optional_state_without_new_overlay(
        self,
    ):
        with patch.object(
            state, "read_state", side_effect=state.OnlyofficeError("private failure")
        ):
            self.assertEqual(
                state.resolve_addon("medilab-test", None, {}, "up"), ([], {})
            )

    def test_acl_loads_child_native_security_module_without_changing_parent_module_path(
        self,
    ):
        inherited = {"PSModulePath": "parent-shell-modules"}
        with (
            patch.dict(os.environ, inherited, clear=True),
            patch.object(
                state.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)
            ) as run,
        ):
            state.windows_acl(self.root / "synthetic marker", create=True)
            self.assertEqual(os.environ["PSModulePath"], inherited["PSModulePath"])
        command = run.call_args.args[0]
        script = base64.b64decode(command[-1]).decode("utf-16-le")
        native_import = "Import-Module -Name (Join-Path $PSHOME 'Modules\\Microsoft.PowerShell.Security\\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop"
        self.assertIn(native_import, script)
        self.assertLess(script.index(native_import), script.index("Set-Acl"))
        self.assertLess(script.index(native_import), script.index("Get-Acl"))
        self.assertEqual(
            {
                key.casefold(): value
                for key, value in run.call_args.kwargs["env"].items()
            }["psmodulepath"],
            inherited["PSModulePath"],
        )
        self.assertEqual(
            command[:4],
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand"],
        )

    def test_engine_capture_decodes_utf8_paths_independently_of_windows_ansi_locale(
        self,
    ):
        payload = '{"path":"C:/MediLab tài liệu/compose.yml"}'
        command = [
            onlyoffice.sys.executable,
            "-c",
            f"import os; os.write(1, bytes.fromhex('{payload.encode().hex()}'))",
        ]
        with patch.object(subprocess, "_text_encoding", return_value="cp1252"):
            self.assertEqual(onlyoffice.run(command).stdout, payload)

    def test_resource_permission_failure_is_never_treated_as_missing(self):
        for message in (
            "permission denied",
            "cannot connect to daemon",
            "timeout",
            "permission denied: no such volume",
        ):
            with (
                self.subTest(message=message),
                patch.object(
                    onlyoffice,
                    "run",
                    return_value=subprocess.CompletedProcess([], 1, "[]", message),
                ),
                self.assertRaises(state.OnlyofficeError),
            ):
                onlyoffice.inspect_resource("volume", "owned")
        with patch.object(
            onlyoffice,
            "run",
            return_value=subprocess.CompletedProcess(
                [], 1, "[]", "Error: no such volume owned"
            ),
        ):
            self.assertIsNone(onlyoffice.inspect_resource("volume", "owned"))

    def test_completed_persistent_volume_is_never_recreated(self):
        with (
            patch.object(
                onlyoffice, "resources", return_value=(["missing-owned-data"], None)
            ),
            patch.object(onlyoffice, "run") as run,
        ):
            with self.assertRaises(state.OnlyofficeError):
                onlyoffice.create_resources({"project": "medilab-test"})
            run.assert_not_called()

    def test_saved_completed_status_does_not_mask_stopped_containers(self):
        addon = {
            "owner": "a" * 32,
            "project": "medilab-test",
            "status": "completed",
            "config": {"MEDILAB_ONLYOFFICE_PORT": "29843"},
        }
        peers = [
            {
                "Config": {
                    "Labels": {
                        "com.docker.compose.project": "medilab-test",
                        state.OWNER_LABEL: addon["owner"],
                        "com.docker.compose.service": service,
                    }
                },
                "State": {"Status": "exited", "Health": {"Status": "healthy"}},
            }
            for service in state.SERVICES
        ]
        with patch.object(
            onlyoffice.bootstrap, "_resources", return_value={"containers": peers}
        ):
            report = onlyoffice.actual_status(addon)
        self.assertEqual(report["saved_status"], "completed")
        self.assertFalse(report["ready"])
        self.assertFalse(
            any(service["running"] for service in report["services"].values())
        )

    def test_foreign_volume_owner_refused_before_creation(self):
        addon = {
            "owner": "a" * 32,
            "project": "medilab-test",
            "config": dict(
                zip(state.CONFIG_KEYS, ("lib", "data", "fonts", "29843"), strict=True)
            ),
        }
        with (
            patch.object(
                onlyoffice.bootstrap, "_resources", return_value={"containers": []}
            ),
            patch.object(
                onlyoffice,
                "inspect_resource",
                return_value={
                    "Labels": {
                        "com.docker.compose.project": "medilab-test",
                        state.OWNER_LABEL: "foreign",
                    }
                },
            ),
            patch.object(onlyoffice, "run") as run,
        ):
            with self.assertRaises(state.OnlyofficeError):
                onlyoffice.create_resources(addon, allow_volumes=True)
            run.assert_not_called()

    def test_standalone_secure_engine_preflight_precedes_owned_marker_reads(self):
        for info in ({"ServerVersion": "27.5.1"}, {"Version": "99.0.0"}):
            with (
                self.subTest(info=info),
                patch.object(onlyoffice, "project_name", return_value="medilab-test"),
                patch.object(
                    onlyoffice.bootstrap, "_assert_local_engine", return_value="local"
                ),
                patch.object(onlyoffice.bootstrap, "_read_marker") as marker,
                patch.object(
                    onlyoffice,
                    "run",
                    return_value=subprocess.CompletedProcess(
                        [], 0, json.dumps(info), ""
                    ),
                ),
                self.assertRaises(state.OnlyofficeError),
            ):
                onlyoffice.selection(secure_engine=True)
            marker.assert_not_called()

    def test_existing_docker_network_requires_ipv4_and_ipv6_isolated_policy(self):
        addon = {
            "owner": "a" * 32,
            "project": "medilab-test",
            "provider": "docker",
            "config": dict(
                zip(state.CONFIG_KEYS, ("lib", "data", "fonts", "29843"), strict=True)
            ),
        }
        labels = {
            "com.docker.compose.project": addon["project"],
            state.OWNER_LABEL: addon["owner"],
        }
        options = {
            f"com.docker.network.bridge.gateway_mode_ipv{version}": "isolated"
            for version in (4, 6)
        }
        for changed in (None, 4, 6, "driver"):
            configured = {
                key: value
                for key, value in options.items()
                if changed is None or not key.endswith(str(changed))
            }
            network = {
                "Labels": labels,
                "Internal": True,
                "Driver": "macvlan" if changed == "driver" else "bridge",
                "Options": configured,
            }
            with (
                self.subTest(missing=changed),
                patch.object(
                    onlyoffice.bootstrap, "_resources", return_value={"containers": []}
                ),
                patch.object(
                    onlyoffice,
                    "inspect_resource",
                    side_effect=lambda kind, _name, selected=network: (
                        selected if kind == "network" else {"Labels": labels}
                    ),
                ),
                patch.object(onlyoffice, "run") as run,
            ):
                if changed is None:
                    onlyoffice.resources(addon)
                else:
                    with self.assertRaises(state.OnlyofficeError):
                        onlyoffice.create_resources(addon)
                    onlyoffice.resources(addon, preparing=True, inspect_policy=False)
                run.assert_not_called()

    def test_external_network_is_created_with_owner_and_isolation_and_never_adopted(
        self,
    ):
        addon = {
            "owner": "a" * 32,
            "base_owner": "base-owner",
            "project": "medilab-test",
            "config": dict(
                zip(state.CONFIG_KEYS, ("lib", "data", "fonts", "29843"), strict=True)
            ),
        }
        own_labels = {
            "com.docker.compose.project": addon["project"],
            state.OWNER_LABEL: addon["owner"],
            onlyoffice.bootstrap.OWNER_LABEL: addon["base_owner"],
        }
        for existing in (
            None,
            {"Labels": {**own_labels, state.OWNER_LABEL: "foreign"}, "Internal": True},
        ):
            with (
                self.subTest(existing=existing is not None),
                patch.object(
                    onlyoffice.bootstrap, "_resources", return_value={"containers": []}
                ),
                patch.object(
                    onlyoffice,
                    "inspect_resource",
                    side_effect=lambda kind, _name, selected=existing: (
                        selected if kind == "network" else {"Labels": own_labels}
                    ),
                ),
                patch.object(onlyoffice, "save"),
                patch.object(
                    onlyoffice,
                    "run",
                    return_value=subprocess.CompletedProcess([], 0, '{"host": {}}', ""),
                ) as run,
            ):
                if existing:
                    with self.assertRaises(state.OnlyofficeError):
                        onlyoffice.create_resources(addon)
                    run.assert_not_called()
                else:
                    onlyoffice.create_resources(addon)
                    command = run.call_args_list[-1].args[0]
                    self.assertEqual(
                        command[:4], ["docker", "network", "create", "--internal"]
                    )
                    self.assertIn(f"{state.OWNER_LABEL}={addon['owner']}", command)
                    self.assertIn(
                        f"{onlyoffice.bootstrap.OWNER_LABEL}={addon['base_owner']}",
                        command,
                    )
                    self.assertIn("com.docker.compose.network=onlyoffice", command)
                    self.assertEqual(
                        command[-3:],
                        ["--opt", "isolate=strict", "medilab-test_onlyoffice"],
                    )
                    self.assertEqual(run.call_count, 2)

    def test_changed_registration_does_not_silently_override_selected_ports(self):
        config = dict(
            zip(state.CONFIG_KEYS, ("lib", "data", "fonts", "29843"), strict=True)
        )
        addon = {"registered": True, "config": config}
        with self.assertRaises(state.OnlyofficeError):
            state.verify_registration(
                addon, None, {**config, "MEDILAB_ONLYOFFICE_PORT": "29844"}
            )

    def test_stop_keeps_adapters_alive_during_document_server_drain(self):
        addon = {"owner": "a" * 32, "project": "medilab-test"}
        peers = [
            {
                "Id": service,
                "Config": {
                    "Labels": {
                        "com.docker.compose.project": addon["project"],
                        state.OWNER_LABEL: addon["owner"],
                        "com.docker.compose.service": service,
                    }
                },
            }
            for service in [*state.SERVICES, "odoo"]
        ]
        with (
            patch.object(
                onlyoffice.bootstrap, "_resources", return_value={"containers": peers}
            ),
            patch.object(onlyoffice, "run") as run,
        ):
            onlyoffice.stop(addon, None, {})
        self.assertEqual(
            [call.args[0][-1] for call in run.call_args_list],
            ["onlyoffice", "onlyoffice-adapter", "onlyoffice-gateway"],
        )
        self.assertIn("1890", run.call_args_list[0].args[0])

    def test_legacy_publisher_handoff_drains_then_removes_only_verified_owned_containers(
        self,
    ):
        addon = {
            "owner": "a" * 32,
            "project": "medilab-test",
            "http_port": 18080,
            "config": {"MEDILAB_ONLYOFFICE_PORT": "29843"},
        }
        peers = [
            {
                "Id": service,
                "Config": {
                    "Labels": {
                        "com.docker.compose.project": addon["project"],
                        state.OWNER_LABEL: addon["owner"],
                        "com.docker.compose.service": service,
                    }
                },
            }
            for service in state.SERVICES
        ]
        mapping = {"18080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "29843"}]}
        peers[1]["HostConfig"] = {
            "NetworkMode": "container:onlyoffice",
            "PortBindings": {},
        }
        peers[1]["NetworkSettings"] = {"Ports": mapping}
        peers[0].update(
            {
                "HostConfig": {"PortBindings": mapping},
                "NetworkSettings": {"Ports": mapping},
                "State": {"Running": True},
            }
        )
        events = []
        with (
            patch.object(
                onlyoffice.bootstrap, "_resources", return_value={"containers": peers}
            ),
            patch.object(
                onlyoffice, "stop", side_effect=lambda *_args: events.append("drain")
            ),
            patch.object(
                onlyoffice, "run", side_effect=lambda args: events.append(args)
            ),
        ):
            onlyoffice.handoff_public_port(addon, None, {})
        self.assertEqual(
            events,
            [
                "drain",
                ["docker", "rm", "onlyoffice-adapter"],
                ["docker", "rm", "onlyoffice"],
                ["docker", "rm", "onlyoffice-gateway"],
            ],
        )
        for change in (
            "foreign-owner",
            "public-address",
            "wrong-port",
            "extra-port",
            "effective-mismatch",
            "gateway-extra",
            "adapter-extra",
            "duplicate-gateway",
            "malformed-bindings",
            "empty-malformed-bindings",
            "empty-malformed-section",
            "new-layout",
        ):
            current = copy.deepcopy(peers)
            server = current[0]
            if change == "foreign-owner":
                server["Config"]["Labels"][state.OWNER_LABEL] = "foreign"
            elif change == "public-address":
                server["HostConfig"]["PortBindings"]["18080/tcp"][0]["HostIp"] = (
                    "0.0.0.0"
                )
            elif change == "wrong-port":
                server["HostConfig"]["PortBindings"]["18080/tcp"][0]["HostPort"] = (
                    "29844"
                )
            elif change == "extra-port":
                server["HostConfig"]["PortBindings"]["443/tcp"] = [
                    {"HostIp": "127.0.0.1", "HostPort": "29845"}
                ]
            elif change == "effective-mismatch":
                server["NetworkSettings"]["Ports"] = {}
            elif change in {"gateway-extra", "adapter-extra"}:
                current[2 if change == "gateway-extra" else 1].setdefault(
                    "HostConfig", {}
                )["PortBindings"] = {
                    "9999/tcp": [{"HostIp": "0.0.0.0", "HostPort": "29999"}]
                }
            elif change == "duplicate-gateway":
                current.append(copy.deepcopy(current[2]))
            elif change == "malformed-bindings":
                current[1]["HostConfig"]["PortBindings"] = "invalid"
            elif change == "empty-malformed-bindings":
                current[1]["HostConfig"]["PortBindings"] = []
            elif change == "empty-malformed-section":
                current[1]["HostConfig"] = []
            else:
                server["HostConfig"]["PortBindings"] = None
                server["NetworkSettings"]["Ports"] = None
                current[1]["NetworkSettings"]["Ports"] = None
                current[2].update(
                    {
                        "HostConfig": {"PortBindings": mapping},
                        "NetworkSettings": {"Ports": mapping},
                        "State": {"Running": True},
                    }
                )
            with (
                self.subTest(change=change),
                patch.object(
                    onlyoffice.bootstrap,
                    "_resources",
                    return_value={"containers": current},
                ),
                patch.object(onlyoffice, "stop") as stop,
                patch.object(onlyoffice, "run") as run,
            ):
                if change == "new-layout":
                    onlyoffice.handoff_public_port(addon, None, {})
                else:
                    with self.assertRaises(state.OnlyofficeError):
                        onlyoffice.handoff_public_port(addon, None, {})
                stop.assert_not_called()
                run.assert_not_called()

    def test_compose_drain_validates_identity_and_holds_owner_lock_through_delegation(
        self,
    ):
        addon = {"project": "medilab-test", "engine": "local"}
        events = []

        @contextmanager
        def lock(*_args):
            events.append("lock")
            try:
                yield
            finally:
                events.append("unlock")

        with (
            patch.object(onlyoffice, "read_state", return_value=addon),
            patch.object(
                onlyoffice.bootstrap, "_assert_local_engine", return_value="local"
            ),
            patch.object(onlyoffice.bootstrap, "_read_compose_env", return_value={}),
            patch.object(onlyoffice, "locked", lock),
            patch.object(
                onlyoffice,
                "verify_registration",
                side_effect=lambda *_args: events.append("registration"),
            ),
            patch.object(
                onlyoffice,
                "resources",
                side_effect=lambda *_args, **_kwargs: events.append("ownership"),
            ),
            patch.object(
                onlyoffice, "stop", side_effect=lambda *_args: events.append("drain")
            ),
            onlyoffice.drained_for_compose("medilab-test", None, {}),
        ):
            events.append("compose-down")
        self.assertEqual(
            events,
            ["lock", "registration", "ownership", "drain", "compose-down", "unlock"],
        )
        with (
            patch.object(onlyoffice, "read_state", return_value=addon),
            patch.object(
                onlyoffice.bootstrap, "_assert_local_engine", return_value="other"
            ),
            patch.object(onlyoffice, "stop") as stop,
            self.assertRaises(state.OnlyofficeError),
            onlyoffice.drained_for_compose("medilab-test", None, {}),
        ):
            self.fail("Foreign engine delegated Compose down")
        stop.assert_not_called()

    def test_down_removes_namespace_consumer_before_server_without_force_or_volumes(
        self,
    ):
        addon = {"project": "medilab-test", "status": "completed"}
        peers = [
            {
                "Id": service,
                "Config": {"Labels": {"com.docker.compose.service": service}},
            }
            for service in state.SERVICES
        ]
        with (
            patch.object(onlyoffice.sys, "argv", ["onlyoffice.py", "down"]),
            patch.object(
                onlyoffice,
                "selection",
                return_value=("medilab-test", None, "local", {}),
            ),
            patch.object(onlyoffice, "read_state", return_value=addon),
            patch.object(onlyoffice, "verify_registration"),
            patch.object(onlyoffice, "resources"),
            patch.object(onlyoffice, "locked", return_value=nullcontext()),
            patch.object(onlyoffice, "stop"),
            patch.object(onlyoffice, "owned_containers", return_value=peers),
            patch.object(onlyoffice, "run") as run,
        ):
            onlyoffice.main()
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ["docker", "rm", service]
                for service in (
                    "onlyoffice-adapter",
                    "onlyoffice",
                    "onlyoffice-gateway",
                )
            ],
        )

    def test_running_image_is_compared_to_the_pinned_digest_identity(self):
        addon = {"owner": "a" * 32, "project": "medilab-test"}
        peer = {
            "Image": "sha256:expected",
            "Config": {
                "Labels": {
                    "com.docker.compose.project": addon["project"],
                    state.OWNER_LABEL: addon["owner"],
                    "com.docker.compose.service": "onlyoffice",
                }
            },
        }
        with (
            patch.object(
                onlyoffice, "inspect_resource", return_value={"Id": "sha256:expected"}
            ),
            patch.object(onlyoffice, "owned_containers", return_value=[peer]),
        ):
            onlyoffice.verify_image(addon)
            peer["Image"] = "sha256:other"
            with self.assertRaises(state.OnlyofficeError):
                onlyoffice.verify_image(addon)

    def test_general_up_cannot_recreate_an_editor_network_without_its_policy(self):
        config = dict(
            zip(state.CONFIG_KEYS, ("lib", "data", "fonts", "29843"), strict=True)
        )
        addon = {
            "owner": "a" * 32,
            "project": "medilab-test",
            "status": "completed",
            "registered": True,
            "engine": "podman",
            "provider": "podman",
            "config": config,
        }
        volumes = [
            {"Name": name, "Labels": {state.OWNER_LABEL: addon["owner"]}}
            for name in ("lib", "data", "fonts")
        ]
        with (
            patch.object(state, "read_state", return_value=addon),
            patch.object(
                onlyoffice.bootstrap, "_assert_local_engine", return_value="podman"
            ),
            patch.object(
                onlyoffice.bootstrap, "_read_compose_env", return_value=config
            ),
            patch.object(
                onlyoffice.bootstrap,
                "_resources",
                return_value={"volumes": volumes, "networks": []},
            ),
            patch.object(state, "runtime_environment") as runtime,
        ):
            self.assertEqual(
                state.resolve_addon("medilab-test", None, {}, "up"), ([], {})
            )
            runtime.assert_not_called()

    def test_ordinary_explicit_and_quoted_persisted_secret_select_the_same_identity(
        self,
    ):
        secret = "Existing-local-only-secret_0123456789"
        for spelling in (
            secret,
            f'"{secret}"',
            f"'{secret}'",
            f'"{secret}" # local configuration',
        ):
            with self.subTest(spelling=spelling):
                file = self.root / "tools/infrastructure/.env"
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(f"export ONLYOFFICE_JWT_SECRET={spelling}\n")
                self.assertEqual(
                    state.configuration_inputs({"ONLYOFFICE_JWT_SECRET": secret}),
                    {"ONLYOFFICE_JWT_SECRET": secret},
                )

    def test_conflicting_or_invalid_explicit_secrets_fail_without_creating_state(self):
        directory = self.root / "tools/infrastructure"
        directory.mkdir(parents=True)
        file = directory / ".env"
        file.write_text(
            'ONLYOFFICE_JWT_SECRET="Existing-local-only-secret_0123456789"\n'
        )
        for value in (
            "",
            "short",
            "invalid quote'" * 5,
            "Different-local-only-secret_9876543210",
        ):
            with (
                self.subTest(value=value),
                self.assertRaises(state.OnlyofficeError) as raised,
            ):
                state.configuration_inputs({"ONLYOFFICE_JWT_SECRET": value})
            self.assertNotIn(value or "unused-marker", str(raised.exception))
            self.assertFalse((self.root / ".local").exists())

    def test_fresh_inputs_ignore_caller_persisted_credentials(self):
        directory = self.root / "tools/infrastructure"
        directory.mkdir(parents=True)
        (directory / ".env").write_text(
            'ONLYOFFICE_JWT_SECRET="Caller-private-secret_0123456789012345"\n'
        )
        self.assertEqual(
            state.configuration_inputs({"MEDILAB_DB_NAME": "medilab"}, fresh=True), {}
        )

    def test_selection_normalizes_quoted_persisted_secret_without_overriding_caller(
        self,
    ):
        secret = "Existing-local-only-secret_0123456789"
        file = self.root / "tools/infrastructure/.env"
        file.parent.mkdir(parents=True)
        file.write_text(f'ONLYOFFICE_JWT_SECRET="{secret}" # local\n')
        with (
            patch.dict(os.environ, {"ONLYOFFICE_JWT_SECRET": secret}, clear=True),
            patch.object(onlyoffice, "project_name", return_value="ordinary"),
            patch.object(onlyoffice.bootstrap, "_read_marker", return_value=None),
            patch.object(
                onlyoffice.bootstrap, "_assert_local_engine", return_value="local"
            ),
            patch.object(
                onlyoffice.bootstrap,
                "_read_compose_env",
                return_value={"ONLYOFFICE_JWT_SECRET": f'"{secret}" # local'},
            ),
        ):
            _, _, _, environment = onlyoffice.selection(
                recovering=True, validate_inputs=True
            )
        self.assertEqual(environment["ONLYOFFICE_JWT_SECRET"], secret)

    def test_fresh_selection_never_uses_inherited_editor_credentials(self):
        marker = {
            "project": "medilab-test",
            "owner": "base",
            "config": {"COMPOSE_PROJECT_NAME": "medilab-test"},
        }
        with (
            patch.dict(
                os.environ,
                {
                    "ONLYOFFICE_JWT_SECRET": "Caller-private-secret_0123456789012345",
                    "ONLYOFFICE_PUBLIC_URL": "https://manual.invalid",
                },
                clear=True,
            ),
            patch.object(onlyoffice, "project_name", return_value="medilab-test"),
            patch.object(onlyoffice.bootstrap, "_read_marker", return_value=marker),
            patch.object(
                onlyoffice.bootstrap, "_assert_local_engine", return_value="local"
            ),
            patch.object(onlyoffice.bootstrap, "_assert_owned_resources"),
            patch.object(onlyoffice.bootstrap, "_validate_completed_selection"),
        ):
            _, _, _, environment = onlyoffice.selection(
                recovering=True, validate_inputs=True
            )
        self.assertNotIn("ONLYOFFICE_JWT_SECRET", environment)
        self.assertNotIn("ONLYOFFICE_PUBLIC_URL", environment)

    def test_manual_runtime_and_explicit_origins_are_refused_before_setup_mutation(
        self,
    ):
        project = "medilab-test"
        manual = {
            "containers": [
                {
                    "Config": {
                        "Labels": {"com.docker.compose.service": "odoo"},
                        "Env": [
                            "ONLYOFFICE_INTERNAL_URL=https://manual.invalid",
                            "ONLYOFFICE_JWT_SECRET=Private-manual-secret_0123456789012345",
                        ],
                    }
                }
            ],
            "networks": [],
            "volumes": [],
        }
        with (
            patch.object(
                onlyoffice, "selection", return_value=(project, None, "local", {})
            ),
            patch.object(onlyoffice.bootstrap, "_resources", return_value=manual),
            patch.object(onlyoffice, "compose") as compose,
            self.assertRaises(state.OnlyofficeError) as raised,
        ):
            onlyoffice.setup()
        self.assertIn("unmanaged", str(raised.exception))
        self.assertNotIn("Private-manual", str(raised.exception))
        self.assertFalse((self.root / ".local").exists())
        compose.assert_not_called()
        with (
            patch.object(onlyoffice.bootstrap, "_resources") as inventory,
            self.assertRaises(state.OnlyofficeError),
        ):
            onlyoffice.guard_existing(
                project, None, {"ONLYOFFICE_PUBLIC_URL": "https://manual.invalid"}
            )
        inventory.assert_not_called()

    def test_project_name_containing_onlyoffice_does_not_make_core_resources_addons(
        self,
    ):
        project = "medilab-onlyoffice"
        core = {
            "containers": [
                {
                    "Name": project + "-odoo-1",
                    "Config": {
                        "Labels": {"com.docker.compose.service": "odoo"},
                        "Env": [],
                    },
                }
            ],
            "volumes": [{"Name": project + "_db"}],
            "networks": [{"name": project + "_default"}],
        }
        with patch.object(onlyoffice.bootstrap, "_resources", return_value=core):
            onlyoffice.guard_existing(
                project,
                None,
                {"ONLYOFFICE_JWT_SECRET": "Existing-local-only-secret_0123456789"},
            )

    def test_initial_setup_and_repeat_preserve_explicit_secret_without_generation(self):
        secret = "Existing-local-only-secret_0123456789"
        project = "medilab-test"
        persisted = {}
        environment = {"ONLYOFFICE_JWT_SECRET": secret}
        inventory = {"containers": [], "networks": [], "volumes": []}

        def prepare(directory, _project, _owner):
            for relative, content in (
                ("tls/public/ca.crt", "synthetic certificate"),
                ("tls/server/tls.crt", "synthetic server certificate"),
            ):
                file = directory / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                if not file.exists():
                    file.write_text(content)

        with ExitStack() as stack:
            for context in (
                patch.object(onlyoffice, "ROOT", self.root),
                patch.object(onlyoffice, "DIRECTORY", self.root / ".local/onlyoffice"),
                patch.object(
                    onlyoffice,
                    "selection",
                    side_effect=lambda **_kwargs: (
                        project,
                        None,
                        "local",
                        dict(environment),
                    ),
                ),
                patch.object(
                    onlyoffice.bootstrap, "_resources", return_value=inventory
                ),
                patch.object(
                    onlyoffice.bootstrap,
                    "_read_compose_env",
                    side_effect=lambda: dict(persisted),
                ),
                patch.object(
                    onlyoffice.bootstrap,
                    "_write_compose_env",
                    side_effect=persisted.update,
                ),
                patch.object(
                    onlyoffice.bootstrap, "_published_ports", return_value=set()
                ),
                patch.object(onlyoffice, "port_available", return_value=True),
                patch("onlyoffice_tls.prepare", side_effect=prepare),
                patch("onlyoffice_tls.verify"),
                patch.object(
                    onlyoffice,
                    "create_resources",
                    side_effect=lambda addon, **_kwargs: addon.setdefault(
                        "provider", "podman"
                    ),
                ),
                patch.object(onlyoffice, "resources"),
                patch.object(onlyoffice, "verify_network"),
                patch.object(onlyoffice, "verify_runtime"),
                patch.object(
                    onlyoffice,
                    "compose",
                    return_value=subprocess.CompletedProcess([], 0, "", ""),
                ),
            ):
                stack.enter_context(context)
            generate = stack.enter_context(
                patch.object(
                    onlyoffice.secrets,
                    "token_urlsafe",
                    side_effect=AssertionError("Existing secret must not be rotated"),
                )
            )
            output = io.StringIO()
            with redirect_stdout(output):
                onlyoffice.setup()
                file = state.state_directory(project) / "jwt"
                original = (file.read_bytes(), file.stat().st_mtime_ns)
                onlyoffice.setup()
            self.assertEqual(original, (file.read_bytes(), file.stat().st_mtime_ns))
            self.assertEqual(file.read_text(), secret)
            self.assertNotIn(secret, output.getvalue())
            self.assertNotIn(secret, json.dumps(persisted))
            self.assertNotIn(secret, (file.parent / "state.json").read_text())
            generate.assert_not_called()
            environment["ONLYOFFICE_JWT_SECRET"] = (
                "Different-local-only-secret_9876543210"
            )
            with self.assertRaises(state.OnlyofficeError):
                onlyoffice.setup()
            self.assertEqual(original, (file.read_bytes(), file.stat().st_mtime_ns))


class EngineBoundaryTest(unittest.TestCase):
    def test_verified_local_podman_endpoint_survives_sanitized_child_environment(self):
        with patch.dict(
            os.environ,
            {
                "CONTAINER_HOST": "unix:///run/local-podman.sock",
                "PAYOS_API_KEY": "FAKE-MUST-NOT-PROPAGATE",
            },
            clear=True,
        ):
            environment = onlyoffice.bootstrap._compose_environment("medilab-test")
        self.assertEqual(environment["CONTAINER_HOST"], "unix:///run/local-podman.sock")
        self.assertNotIn("PAYOS_API_KEY", environment)

    def test_remote_named_pipes_and_unix_authorities_are_not_local(self):
        for endpoint in (
            "npipe://remote-host/pipe/docker",
            "npipe:////remote-host/pipe/docker",
            "unix://remote-host/run/docker.sock",
            "ssh://localhost/run/docker.sock",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertFalse(
                    onlyoffice.bootstrap._is_local_engine_endpoint(endpoint)
                )
        self.assertTrue(
            onlyoffice.bootstrap._is_local_engine_endpoint(
                "npipe:////./pipe/docker_engine"
            )
        )

    def test_podman_default_remote_cannot_be_masked_by_ignored_docker_host(self):
        values = [
            subprocess.CompletedProcess([], 0, "podman version 6.1.4", ""),
            subprocess.CompletedProcess(
                [], 0, json.dumps({"host": {"serviceIsRemote": True}}), ""
            ),
        ]
        with (
            patch.dict(
                os.environ, {"DOCKER_HOST": "unix:///run/docker.sock"}, clear=True
            ),
            patch.object(onlyoffice.bootstrap, "_run", side_effect=values),
            self.assertRaises(onlyoffice.bootstrap.BootstrapError),
        ):
            onlyoffice.bootstrap._assert_local_engine()

    def test_only_explicit_local_podman_endpoint_can_allow_remote_client_mode(self):
        values = [
            subprocess.CompletedProcess([], 0, "podman version 6.1.4", ""),
            subprocess.CompletedProcess(
                [], 0, json.dumps({"host": {"serviceIsRemote": True}}), ""
            ),
        ]
        with (
            patch.dict(
                os.environ,
                {"CONTAINER_HOST": "unix:///run/user/1000/podman.sock"},
                clear=True,
            ),
            patch.object(onlyoffice.bootstrap, "_run", side_effect=values),
        ):
            self.assertEqual(
                onlyoffice.bootstrap._assert_local_engine(),
                "unix:///run/user/1000/podman.sock",
            )

    def test_podman_local_requires_actual_boolean_evidence(self):
        for remote in (False, "false", None):
            values = [
                subprocess.CompletedProcess([], 0, "podman version 6.1.4", ""),
                subprocess.CompletedProcess(
                    [], 0, json.dumps({"host": {"serviceIsRemote": remote}}), ""
                ),
            ]
            with (
                self.subTest(remote=remote),
                patch.dict(os.environ, {}, clear=True),
                patch.object(onlyoffice.bootstrap, "_run", side_effect=values),
            ):
                if remote is False:
                    self.assertEqual(
                        onlyoffice.bootstrap._assert_local_engine(), "podman"
                    )
                else:
                    with self.assertRaises(onlyoffice.bootstrap.BootstrapError):
                        onlyoffice.bootstrap._assert_local_engine()

    def test_remote_connection_selectors_fail_before_any_engine_request(self):
        for environment in (
            {"CONTAINER_CONNECTION": "production"},
            {"CONTAINER_HOST": "ssh://server"},
            {
                "CONTAINER_HOST": "unix:///local.sock",
                "DOCKER_HOST": "tcp://production:2375",
            },
        ):
            with (
                self.subTest(environment=environment),
                patch.dict(os.environ, environment, clear=True),
                patch.object(onlyoffice.bootstrap, "_run") as run,
            ):
                with self.assertRaises(onlyoffice.bootstrap.BootstrapError):
                    onlyoffice.bootstrap._assert_local_engine()
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
