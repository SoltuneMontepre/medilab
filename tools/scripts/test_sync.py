import contextlib
import errno
import io
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import sync
from host_tools import HostError


class SyncTasksTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sync contracts ")
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.app = self.root / "src/applications/medilab-sync"
        self.app.mkdir(parents=True)
        self.metadata = self.root / ".local/sync-development.json"
        for name, value in (
            ("ROOT", self.root),
            ("APP", self.app),
            ("METADATA", self.metadata),
        ):
            replacement = patch.object(sync, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)

    def test_setup_is_frozen_and_keeps_installed_profile_untouched(self):
        profile = self.root / "installed profile"
        profile.mkdir()
        original = {
            name: f"owned-{name}"
            for name in ("sync.sqlite", "device.apikey", "binding.json")
        }
        for name, value in original.items():
            (profile / name).write_text(value, encoding="utf-8")
        commands = []
        with (
            patch.object(sync, "doctor", return_value={}),
            patch.object(
                sync, "selected_odoo_url", return_value="http://localhost:8069/prefix"
            ),
            patch.object(sync, "_locked_cli"),
            patch.object(sync, "verify") as verify,
            patch.object(sync, "executable", side_effect=lambda name: name),
            patch.object(sync, "run") as cargo,
            patch.object(
                sync,
                "_bun",
                side_effect=lambda argv, env, **_kwargs: commands.append((argv, env)),
            ),
        ):
            sync.execute("setup")
        self.assertEqual(
            [argv for argv, _env in commands],
            [["install", "--frozen-lockfile", "--ignore-scripts"], ["run", "build"]],
        )
        self.assertEqual(
            [call.args[0] for call in cargo.call_args_list],
            [
                ["cargo", action, "--locked", "--manifest-path", sync.MANIFEST]
                for action in ("fetch", "check")
            ],
        )
        verify.assert_called_once_with("http://localhost:8069/prefix")
        self.assertTrue(
            all(
                (
                    env["MEDILAB_SYNC_ODOO_URL"] == "http://localhost:8069/prefix"
                    for _argv, env in commands
                )
            )
        )
        self.assertEqual(
            {name: (profile / name).read_text(encoding="utf-8") for name in original},
            original,
        )
        self.assertEqual(
            json.loads(self.metadata.read_text(encoding="utf-8"))["odoo_url"],
            "http://localhost:8069/prefix",
        )

    def test_dependency_failure_stops_before_build_metadata_or_profile_changes(self):
        failure = subprocess.CalledProcessError(7, ["bun", "install"])
        with (
            patch.object(sync, "doctor", return_value={}),
            patch.object(
                sync, "selected_odoo_url", return_value="http://localhost:8069"
            ),
            patch.object(sync, "_bun", side_effect=failure) as bun,
            patch.object(sync, "_locked_cli") as cli,
            self.assertRaises(subprocess.CalledProcessError),
        ):
            sync.execute("setup")
        self.assertEqual(bun.call_count, 1)
        cli.assert_not_called()
        self.assertFalse(self.metadata.exists())

    def test_doctor_does_not_require_or_create_a_selected_environment(self):
        with (
            patch.object(sync, "doctor", return_value={}),
            patch.object(sync, "selected_odoo_url") as selected,
        ):
            sync.execute("doctor")
        selected.assert_not_called()
        self.assertFalse(self.metadata.exists())

    def test_verify_checks_native_prerequisites_and_selected_api_without_profile_mutations(
        self,
    ):
        with (
            patch.object(sync, "doctor") as doctor,
            patch.object(
                sync, "selected_odoo_url", return_value="http://localhost:8069/prefix"
            ),
            patch.object(sync, "verify") as verify,
        ):
            sync.execute("verify")
        doctor.assert_called_once_with()
        verify.assert_called_once_with("http://localhost:8069/prefix")
        self.assertFalse(self.metadata.exists())

    def test_verify_missing_native_prerequisite_fails_before_api_probe(self):
        with (
            patch.object(sync, "doctor", side_effect=HostError("Cargo missing")),
            patch.object(sync, "verify") as verify,
            self.assertRaisesRegex(HostError, "Cargo missing"),
        ):
            sync.execute("verify")
        verify.assert_not_called()
        self.assertFalse(self.metadata.exists())

    def test_network_operations_require_owned_selection_before_mutation_or_native_launch(
        self,
    ):
        for operation in ("setup", "verify", "dev"):
            with (
                self.subTest(operation=operation),
                patch.object(sync, "doctor", return_value={}),
                patch.object(
                    sync,
                    "selected_odoo_url",
                    side_effect=HostError("No saved local selection"),
                ) as selected,
                patch.object(sync, "verify") as api,
                patch.object(sync, "_bun") as bun,
                patch.object(sync, "run") as run,
                patch.object(sync, "_locked_cli") as cli,
                self.assertRaisesRegex(HostError, "No saved local selection"),
            ):
                sync.execute(operation)
            selected.assert_called_once_with(require_saved_selection=True)
            api.assert_not_called()
            bun.assert_not_called()
            run.assert_not_called()
            cli.assert_not_called()
            self.assertFalse(self.metadata.exists())

    def test_offline_build_and_checks_do_not_require_a_running_backend(self):
        for operation in ("build", "test", "lint", "check"):
            with (
                self.subTest(operation=operation),
                patch.object(sync, "doctor", return_value={}),
                patch.object(
                    sync, "selected_odoo_url", return_value="http://localhost:8069"
                ) as selected,
                patch.object(sync, "verify") as api,
                patch.object(sync, "_locked_cli"),
                patch.object(sync, "executable", side_effect=lambda name: name),
                patch.object(sync, "_bun"),
                patch.object(sync, "run"),
            ):
                sync.execute(operation)
            selected.assert_called_once_with(require_saved_selection=False)
            api.assert_not_called()
            self.assertFalse(self.metadata.exists())

    def test_setup_api_failure_keeps_existing_metadata_and_cannot_report_completion(
        self,
    ):
        self.metadata.parent.mkdir()
        original = json.dumps(
            {
                "version": 1,
                "worktree": str(self.root),
                "odoo_url": "http://localhost:8069/old",
            }
        )
        self.metadata.write_text(original, encoding="utf-8")
        output = io.StringIO()
        with (
            patch.object(sync.sys, "argv", ["sync.py", "setup"]),
            patch.object(sync, "doctor", return_value={}),
            patch.object(
                sync, "selected_odoo_url", return_value="http://localhost:8069/new"
            ),
            patch.object(sync, "_locked_cli"),
            patch.object(sync, "executable", side_effect=lambda name: name),
            patch.object(sync, "_bun"),
            patch.object(sync, "run"),
            patch.object(
                sync, "verify", side_effect=HostError("Selected API is unavailable")
            ),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(sync.main(), 1)
        self.assertEqual(self.metadata.read_text(encoding="utf-8"), original)
        self.assertNotIn("completed", output.getvalue())

    def test_setup_locked_crate_check_failure_stops_api_metadata_and_success(self):
        self.metadata.parent.mkdir()
        original = json.dumps(
            {
                "version": 1,
                "worktree": str(self.root),
                "odoo_url": "http://localhost:8069/old",
            }
        )
        self.metadata.write_text(original, encoding="utf-8")
        output = io.StringIO()

        def cargo(argv, **_kwargs):
            if argv[1] == "check":
                raise subprocess.CalledProcessError(42, argv)

        with (
            patch.object(sync.sys, "argv", ["sync.py", "setup"]),
            patch.object(sync, "doctor", return_value={}),
            patch.object(
                sync, "selected_odoo_url", return_value="http://localhost:8069"
            ),
            patch.object(sync, "_locked_cli"),
            patch.object(sync, "executable", side_effect=lambda name: name),
            patch.object(sync, "_bun"),
            patch.object(sync, "run", side_effect=cargo),
            patch.object(sync, "verify") as api,
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(sync.main(), 42)
        api.assert_not_called()
        self.assertEqual(self.metadata.read_text(encoding="utf-8"), original)
        self.assertNotIn("completed", output.getvalue())

    def test_build_creates_platform_release_packages_with_locked_cargo(self):
        for system, bundles in (("Linux", "deb,rpm"), ("Windows", "nsis")):
            with (
                self.subTest(system=system),
                patch.object(sync.platform, "system", return_value=system),
                patch.object(sync, "doctor", return_value={}),
                patch.object(
                    sync, "selected_odoo_url", return_value="http://localhost:8069"
                ),
                patch.object(sync, "_locked_cli"),
                patch.object(sync, "_bun") as bun,
            ):
                sync.execute("build")
            self.assertEqual(
                bun.call_args.args[0],
                ["run", "tauri", "build", "--bundles", bundles, "--", "--locked"],
            )

    def test_dev_launches_tauri_after_gui_and_port_checks(self):
        order = []
        with (
            patch.object(
                sync,
                "doctor",
                side_effect=lambda **kwargs: order.append(("doctor", kwargs)) or {},
            ),
            patch.object(
                sync, "selected_odoo_url", return_value="http://localhost:8069"
            ),
            patch.object(sync, "_locked_cli"),
            patch.object(
                sync,
                "_free_dev_ports",
                side_effect=lambda: order.append(("ports", None)),
            ),
            patch.object(
                sync, "_bun", side_effect=lambda argv, _env: order.append(("bun", argv))
            ),
        ):
            sync.execute("dev")
        self.assertEqual(
            order,
            [("doctor", {"gui": True}), ("ports", None), ("bun", ["run", "tauri:dev"])],
        )

    def test_dev_refuses_an_ipv6_only_loopback_port_collision(self):
        def bind(address):
            if address[0] == "::1":
                raise OSError(errno.EADDRINUSE, "already used")

        probe = Mock()
        probe.bind.side_effect = bind
        manager = Mock(
            __enter__=Mock(return_value=probe), __exit__=Mock(return_value=False)
        )
        with (
            patch.object(sync.socket, "socket", return_value=manager),
            self.assertRaisesRegex(HostError, "1420"),
        ):
            sync._free_dev_ports()
        self.assertEqual(
            [call.args[0] for call in probe.bind.call_args_list],
            [("127.0.0.1", 1420), ("::1", 1420)],
        )

    def test_dev_can_probe_ipv4_when_ipv6_is_disabled(self):
        addresses = []

        def bind(address):
            addresses.append(address)
            if address[0] == "::1":
                raise OSError(errno.EAFNOSUPPORT, "IPv6 disabled")

        probe = Mock(bind=Mock(side_effect=bind))
        manager = Mock(
            __enter__=Mock(return_value=probe), __exit__=Mock(return_value=False)
        )
        with patch.object(sync.socket, "socket", return_value=manager):
            sync._free_dev_ports()
        self.assertEqual(
            addresses,
            [("127.0.0.1", 1420), ("::1", 1420), ("127.0.0.1", 1421), ("::1", 1421)],
        )

    def test_frontend_assets_are_built_before_rust_tests_and_failures_stop_the_chain(
        self,
    ):
        order = []
        with (
            patch.object(sync, "doctor", return_value={}),
            patch.object(
                sync, "selected_odoo_url", return_value="http://localhost:8069"
            ),
            patch.object(sync, "_locked_cli"),
            patch.object(sync, "executable", side_effect=lambda name: name),
            patch.object(
                sync, "_bun", side_effect=lambda argv, _env: order.append(argv)
            ),
            patch.object(
                sync, "run", side_effect=lambda argv, **_kwargs: order.append(argv)
            ),
        ):
            sync.execute("test")
        self.assertEqual(
            order,
            [
                ["run", "build"],
                ["test"],
                ["cargo", "test", "--locked", "--manifest-path", sync.MANIFEST],
            ],
        )
        with (
            patch.object(sync, "doctor", return_value={}),
            patch.object(
                sync, "selected_odoo_url", return_value="http://localhost:8069"
            ),
            patch.object(sync, "_locked_cli"),
            patch.object(
                sync, "_bun", side_effect=subprocess.CalledProcessError(3, ["bun"])
            ),
            patch.object(sync, "run") as run,
            self.assertRaises(subprocess.CalledProcessError),
        ):
            sync.execute("test")
        run.assert_not_called()

    def test_clean_removes_fixed_outputs_only_and_needs_no_compiler(self):
        for relative in ("dist", "src-tauri/target", "node_modules", "profile"):
            directory = self.app / relative
            directory.mkdir(parents=True)
            (directory / "keep").write_text(relative)
        with patch.object(sync, "doctor") as doctor:
            sync.execute("clean")
        doctor.assert_not_called()
        self.assertFalse((self.app / "dist").exists())
        self.assertFalse((self.app / "src-tauri/target").exists())
        self.assertEqual(
            (self.app / "profile/keep").read_text(encoding="utf-8"), "profile"
        )
        self.assertEqual(
            (self.app / "node_modules/keep").read_text(encoding="utf-8"), "node_modules"
        )

    def test_clean_refuses_symlink_escape_before_removing_any_other_output(self):
        external = self.root / "external"
        external.mkdir()
        (external / "original").write_text("preserve")
        dist = self.app / "dist"
        dist.mkdir()
        (dist / "original").write_text("preserve")
        target = self.app / "src-tauri/target"
        target.parent.mkdir()
        try:
            target.symlink_to(external, target_is_directory=True)
        except OSError:
            self.skipTest(
                "This account cannot create a test symlink; native junction coverage is separate."
            )
        with self.assertRaises(HostError):
            sync.clean()
        self.assertEqual(
            (external / "original").read_text(encoding="utf-8"), "preserve"
        )
        self.assertEqual((dist / "original").read_text(encoding="utf-8"), "preserve")

    def test_clean_refuses_junction_components(self):
        with (
            patch.object(pathlib.Path, "is_junction", create=True, return_value=True),
            self.assertRaises(HostError),
        ):
            sync.clean()

    def test_foreign_metadata_is_not_overwritten(self):
        self.metadata.parent.mkdir()
        original = '{"version":1,"worktree":"another-worktree"}'
        self.metadata.write_text(original, encoding="utf-8")
        with self.assertRaises(HostError):
            sync.save_endpoint("http://localhost:8069")
        self.assertEqual(self.metadata.read_text(encoding="utf-8"), original)

    def test_locked_cli_requires_the_exact_lockfile_version(self):
        (self.app / "node_modules").mkdir()
        (self.app / "bun.lock").write_text(
            '{"@tauri-apps/cli":["@tauri-apps/cli@2.11.4", ""]}'
        )
        for version in ("2.11.4", "2.11.5"):
            with (
                self.subTest(version=version),
                patch.object(
                    sync, "_bun", return_value=Mock(stdout=f"tauri-cli {version}\n")
                ),
            ):
                if version == "2.11.4":
                    sync._locked_cli({})
                else:
                    with self.assertRaises(HostError):
                        sync._locked_cli({})

    def test_cli_keeps_tool_failure_status_without_exposing_command_secrets(self):
        stream = io.StringIO()
        failure = subprocess.CalledProcessError(
            17, ["tool", "FAKE-SECRET"], stderr="FAKE-SECRET"
        )
        with (
            patch.object(sync.sys, "argv", ["sync.py", "test"]),
            patch.object(sync, "execute", side_effect=failure),
            contextlib.redirect_stderr(stream),
        ):
            self.assertEqual(sync.main(), 17)
        self.assertNotIn("FAKE-SECRET", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
