"""Native acceptance contracts use owned temporary trees and never initialize a runtime."""

import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import windows_acceptance as acceptance
import windows_acceptance_host as host


def copy_collector(root):
    scripts = root / "tools/scripts"
    shutil.copytree(
        Path(__file__).parent,
        scripts,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    core = root / "src/core"
    core.mkdir(parents=True)
    shutil.copyfile(
        Path(__file__).resolve().parents[2] / "src/core/modules.txt",
        core / "modules.txt",
    )
    return scripts


class HostIdentityTests(unittest.TestCase):
    def identity(self, metadata, shell="7.4.6"):
        with (
            patch.object(host.platform, "system", return_value="Windows"),
            patch.object(host, "_native_metadata", return_value=metadata) as read,
        ):
            result = host.host_identity(shell)
            read.assert_called_once_with()
            return result

    def test_server_build_is_not_windows11(self):
        for caption, build, product_type in (
            ("Microsoft Windows Server 2025 Datacenter", 26100, 3),
            ("Microsoft Windows 11 Pro", 26100, 3),
            ("Microsoft Windows 10 Pro", 19045, 1),
            ("Microsoft Windows 11 Pro", 19045, 1),
        ):
            with self.subTest(caption=caption, build=build, product_type=product_type):
                self.assertFalse(
                    self.identity(
                        {
                            "caption": caption,
                            "build": build,
                            "product_type": product_type,
                        }
                    )["windows11"]
                )

    def test_native_windows11_requires_typed_metadata_and_supported_shell(self):
        valid = {
            "caption": "Microsoft Windows 11 Pro",
            "build": 26100,
            "product_type": 1,
        }
        for shell in ("5.1.26100.1", "7.4.6"):
            self.assertTrue(self.identity(valid, shell)["windows11"])
        for document in (
            {**valid, "build": "26100"},
            {**valid, "product_type": True},
            {**valid, "caption": None},
        ):
            with self.subTest(document=document), self.assertRaises(host.HostError):
                self.identity(document)
        with self.assertRaises(host.HostError):
            self.identity(valid, "5.0")

    def test_non_windows_does_not_query_tools(self):
        with (
            patch.object(host.platform, "system", return_value="Linux"),
            patch.object(host, "run") as invoke,
        ):
            self.assertFalse(host.host_identity("")["windows11"])
            invoke.assert_not_called()

    def test_client_build_identifies_windows11_with_a_legacy_registry_caption(self):
        self.assertTrue(
            self.identity(
                {
                    "caption": "Windows 10 Pro",
                    "build": 26100,
                    "product_type": 1,
                }
            )["windows11"]
        )


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="Windows kiểm tra ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    @unittest.skipIf(os.name == "nt", "native shell refusal is covered on Windows")
    def test_collector_subprocess_reaches_the_host_guard_without_writes(self):
        scripts = copy_collector(self.root)
        before = sorted(
            str(path.relative_to(self.root)) for path in self.root.rglob("*")
        )
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-X",
                "utf8",
                str(scripts / "windows_acceptance.py"),
                "--shell-version",
                "7.4.6",
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["host"]["windows11"])
        self.assertEqual(
            sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*")),
            before,
        )

    def test_default_doctor_never_creates_files_or_claims_acceptance(self):
        before = list(self.root.rglob("*"))
        with (
            patch.object(acceptance, "host_identity", return_value={"windows11": True}),
            patch.object(
                acceptance, "prerequisite_inventory", return_value={"native_sync": {}}
            ),
            patch.object(acceptance, "execute_setup") as setup,
        ):
            report, code = acceptance.collect(root=self.root, shell_version="7.4")
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "doctor_passed")
        self.assertEqual(report["acceptance"], "unverified")
        setup.assert_not_called()
        self.assertEqual(list(self.root.rglob("*")), before)

    def test_server_run_setup_blocks_before_inventory_task_or_output(self):
        with (
            patch.object(
                acceptance,
                "host_identity",
                return_value={"windows11": False, "product_type": 3},
            ),
            patch.object(acceptance, "prerequisite_inventory") as inventory,
            patch.object(acceptance, "execute_setup") as setup,
        ):
            report, code = acceptance.collect(run_setup=True, root=self.root)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["acceptance"], "unverified")
        inventory.assert_not_called()
        setup.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_doctor_failure_is_nonzero_and_hides_raw_child_output(self):
        with (
            patch.object(acceptance, "host_identity", return_value={"windows11": True}),
            patch.object(
                acceptance,
                "prerequisite_inventory",
                side_effect=subprocess.CalledProcessError(
                    5, ["private"], output="SECRET"
                ),
            ),
        ):
            report, code = acceptance.collect(root=self.root)
        self.assertEqual(code, 1)
        self.assertNotIn("SECRET", json.dumps(report))
        self.assertNotEqual(report["acceptance"], "passed")

    def test_evidence_is_exclusive_private_and_atomic_failure_preserves_old_bytes(self):
        evidence = acceptance.Evidence(self.root)
        report = {"acceptance": "unverified"}
        evidence.write(report)
        path = evidence.directory / "evidence.json"
        original = path.read_bytes()
        with (
            patch.object(acceptance.os, "replace", side_effect=OSError("injected")),
            self.assertRaises(OSError),
        ):
            evidence.write({"acceptance": "passed"})
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(evidence.directory.glob(".evidence-*")), [])
        evidence.create("test.log", b"original")
        with self.assertRaises(FileExistsError):
            evidence.create("test.log", b"replacement")
        self.assertEqual((evidence.directory / "test.log").read_bytes(), b"original")
        if os.name != "nt":
            self.assertEqual(path.stat().st_mode & 0o077, 0)

    @unittest.skipIf(os.name == "nt", "POSIX symlink and mode contract")
    def test_foreign_output_links_and_writable_ancestors_refused_without_repair(self):
        foreign = self.root / "foreign"
        foreign.mkdir()
        foreign_file = foreign / "evidence.json"
        foreign_file.write_bytes(b"preserve")
        (self.root / ".local").symlink_to(foreign, target_is_directory=True)
        with self.assertRaises(RuntimeError):
            acceptance.Evidence(self.root)
        self.assertEqual(foreign_file.read_bytes(), b"preserve")
        (self.root / ".local").unlink()
        (self.root / ".local").mkdir(mode=0o777)
        (self.root / ".local").chmod(0o777)
        with self.assertRaises(RuntimeError):
            acceptance.Evidence(self.root)
        self.assertEqual((self.root / ".local").stat().st_mode & 0o777, 0o777)

    def test_child_environment_excludes_credentials_and_does_not_change_caller(self):
        evidence = acceptance.Evidence(self.root)
        original = dict(os.environ)
        with patch.dict(
            os.environ,
            {
                "DOPPLER_TOKEN": "secret",
                "JWT_SECRET": "secret",
                "RUSTUP_AUTO_INSTALL": "1",
            },
        ):
            caller = dict(os.environ)
            environment = acceptance.setup_environment(evidence)
            self.assertEqual(dict(os.environ), caller)
        self.assertEqual(dict(os.environ), original)
        self.assertNotIn("DOPPLER_TOKEN", environment)
        self.assertNotIn("JWT_SECRET", environment)
        self.assertEqual(environment["RUSTUP_AUTO_INSTALL"], "0")
        self.assertEqual(Path(environment["MEDILAB_SETUP_DOTENV"]).read_bytes(), b"")
        guard = Path(environment["PATH"].split(os.pathsep)[0])
        self.assertEqual((guard / "bash.cmd").read_bytes(), b"@exit /b 97\r\n")
        self.assertEqual((guard / "sh.cmd").read_bytes(), b"@exit /b 97\r\n")
        for entry in environment["PATH"].split(os.pathsep):
            self.assertFalse(acceptance.BASH_PATH.search(entry))

    def git_result(self, *arguments):
        if arguments[0] == "ls-files":
            return ""
        values = {
            ("status", "--porcelain"): "",
            ("rev-parse", "--absolute-git-dir"): str(
                self.root / "common/worktrees/owned"
            ),
            ("rev-parse", "--path-format=absolute", "--git-common-dir"): str(
                self.root / "common"
            ),
        }
        return values[arguments]

    def test_empty_linked_worktree_checks_both_namespaces_before_creating_files(self):
        (self.root / ".git").write_text("gitdir: owned", encoding="utf-8")
        before = sorted(path.name for path in self.root.iterdir())
        with (
            patch.object(
                acceptance,
                "git",
                side_effect=lambda root, *arguments: self.git_result(*arguments),
            ),
            patch.object(acceptance.bootstrap, "_assert_local_engine"),
            patch("compose_env.project_name", return_value="ordinary"),
            patch.object(acceptance.local_setup, "fresh_project", return_value="fresh"),
            patch.object(acceptance.bootstrap, "_assert_no_resources") as empty,
        ):
            self.assertEqual(acceptance.require_empty_worktree(self.root), "fresh")
        self.assertEqual(
            {call.args[0] for call in empty.call_args_list}, {"ordinary", "fresh"}
        )
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), before)

    def test_existing_configuration_and_non_worktree_refused_before_engine(self):
        (self.root / ".git").write_text("gitdir: owned", encoding="utf-8")
        (self.root / ".env").write_bytes(b"must preserve")
        with (
            patch.object(
                acceptance,
                "git",
                side_effect=lambda root, *arguments: self.git_result(*arguments),
            ),
            patch.object(acceptance.bootstrap, "_assert_local_engine") as engine,
        ):
            with self.assertRaises(acceptance.AcceptanceError):
                acceptance.require_empty_worktree(self.root)
            engine.assert_not_called()
        self.assertEqual((self.root / ".env").read_bytes(), b"must preserve")
        (self.root / ".env").unlink()
        with (
            patch.object(
                acceptance,
                "git",
                side_effect=lambda root, *arguments: (
                    "" if arguments[0] == "status" else str(self.root)
                ),
            ),
            patch.object(acceptance.bootstrap, "_assert_local_engine") as engine,
            self.assertRaises(acceptance.AcceptanceError),
        ):
            acceptance.require_empty_worktree(self.root)
        engine.assert_not_called()

    def test_clean_tracked_source_configuration_is_allowed_but_local_config_is_not(
        self,
    ):
        (self.root / ".git").write_text("gitdir: owned", encoding="utf-8")
        source = self.root / "src/core/.env.local"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"committed source defaults")
        doppler = self.root / "doppler.yaml"
        doppler.write_bytes(b"committed project selection")

        def tracked(root, *arguments):
            if arguments[0] == "ls-files":
                return (
                    arguments[-1]
                    if arguments[-1] in {"src/core/.env.local", "doppler.yaml"}
                    else ""
                )
            return self.git_result(*arguments)

        with (
            patch.object(acceptance, "git", side_effect=tracked),
            patch.object(acceptance.bootstrap, "_assert_local_engine"),
            patch("compose_env.project_name", return_value="ordinary"),
            patch.object(acceptance.local_setup, "fresh_project", return_value="fresh"),
            patch.object(acceptance.bootstrap, "_assert_no_resources"),
        ):
            self.assertEqual(acceptance.require_empty_worktree(self.root), "fresh")
            (self.root / ".env.local").write_bytes(b"local private config")
            with self.assertRaises(acceptance.AcceptanceError):
                acceptance.require_empty_worktree(self.root)
        self.assertEqual(source.read_bytes(), b"committed source defaults")
        self.assertEqual(doppler.read_bytes(), b"committed project selection")

    def run_flow(self, *, codes=None, captures=None):
        package = (
            self.root
            / "src/applications/medilab-sync/src-tauri/target/release/bundle/nsis/owned.exe"
        )
        package.parent.mkdir(parents=True, exist_ok=True)
        package.write_bytes(b"owned NSIS fixture")
        baseline = {"bucket": {"objects": 13, "sha256": "a"}, "data": {"rows": 6}}
        report = {"stages": []}
        with (
            patch.object(acceptance, "require_empty_worktree", return_value="fresh"),
            patch.object(
                acceptance,
                "source_identity",
                return_value={"head": "owned", "tracked_sha256": "a"},
            ),
            patch.object(acceptance, "verify_frozen") as frozen,
            patch.object(acceptance, "selected_owner", return_value="owner"),
            patch.object(acceptance.snapshots, "selected"),
            patch.object(acceptance.snapshots, "ready_baseline", return_value=baseline),
            patch.object(
                acceptance.snapshots,
                "capture",
                side_effect=captures if captures is not None else None,
                return_value=baseline,
            ),
            patch.object(
                acceptance,
                "run_stage",
                side_effect=codes if codes is not None else None,
                return_value=0,
            ) as commands,
        ):
            try:
                acceptance.execute_setup(self.root, report)
            except acceptance.AcceptanceError as error:
                return report, commands, frozen, error
        return report, commands, frozen, None

    def test_full_sequence_is_native_nondestructive_and_checks_every_repeat(self):
        report, commands, frozen, error = self.run_flow()
        self.assertIsNone(error)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["gui_acceptance"], "unverified")
        self.assertEqual(
            [call.args[0] for call in commands.call_args_list],
            [command for _, command in acceptance.STAGES],
        )
        self.assertEqual(report["integrity_verified_after"], "sync_build")
        self.assertEqual(len(report["packages"]), 1)
        self.assertEqual(
            set(report["stage_snapshots"]),
            {name for name, _command in acceptance.STAGES},
        )
        self.assertTrue(all(not diff for diff in report["integrity_diffs"].values()))
        self.assertEqual(frozen.call_count, 14)
        self.assertNotIn("secret", json.dumps(report).lower())

    def test_command_failure_stops_following_stages_and_records_integrity(self):
        report, commands, _frozen, error = self.run_flow(codes=[0, 23])
        self.assertIsNotNone(error)
        self.assertEqual(commands.call_count, 2)
        self.assertTrue(report["failure_integrity_unchanged"])
        self.assertNotEqual(report.get("acceptance"), "passed")
        self.assertEqual(report["stages"][-1]["exit"], 23)
        self.assertEqual(report["failure_snapshot"]["snapshot"], report["baseline"])

    def test_failed_snapshot_read_does_not_mask_original_command_nonzero(self):
        report, commands, _frozen, error = self.run_flow(
            codes=[0, 23],
            captures=[acceptance.snapshots.SnapshotError("private probe failed")],
        )
        self.assertEqual(commands.call_count, 2)
        self.assertIn("command failed", str(error))
        self.assertEqual(report["stages"][-1]["exit"], 23)
        self.assertEqual(report["failure_snapshot"]["error_type"], "SnapshotError")
        self.assertNotIn("private probe failed", json.dumps(report))

    def test_failed_command_retains_actual_snapshot_and_failed_evidence_write_preserves_original_exit(
        self,
    ):
        current = {"bucket": {"objects": 14, "sha256": "changed"}}
        report, commands, _frozen, error = self.run_flow(
            codes=[0, 23], captures=[current]
        )
        self.assertEqual(commands.call_count, 2)
        self.assertIn("command failed", str(error))
        self.assertEqual(report["failure_snapshot"]["snapshot"], current)
        self.assertIn("bucket", report["failure_snapshot"]["integrity_diff"])
        self.assertFalse(report["failure_integrity_unchanged"])

        def failed_publication(evidence, report):
            if report["stages"] and report["stages"][-1].get("exit") == 23:
                raise OSError("synthetic full evidence disk")

        with patch.object(
            acceptance.Evidence, "write", autospec=True, side_effect=failed_publication
        ):
            report, _commands, _frozen, error = self.run_flow(codes=[0, 23])
        self.assertIn("command failed", str(error))
        self.assertEqual(report["stages"][-1]["exit"], 23)
        self.assertTrue(report["failure_snapshot_evidence_write_failed"])

    def test_data_or_secret_or_volume_drift_stops_without_restoring_over_it(self):
        for kind in ("bucket", "private_identity_hashes", "volumes", "data"):
            with self.subTest(kind=kind):
                report, commands, _frozen, error = self.run_flow(
                    captures=[{kind: "changed"}]
                )
                self.assertIsNotNone(error)
                self.assertEqual(commands.call_count, 2)
                self.assertNotEqual(report.get("acceptance"), "passed")
                self.assertEqual(
                    report["stage_snapshots"]["repeated_setup"], {kind: "changed"}
                )
                self.assertIn(kind, report["integrity_diffs"]["repeated_setup"])
                saved = json.loads(
                    (self.root / report["evidence"]).read_text(encoding="utf-8")
                )
                self.assertEqual(saved["stage_snapshots"], report["stage_snapshots"])
                self.assertEqual(saved["integrity_diffs"], report["integrity_diffs"])

    def test_source_change_is_rejected(self):
        with (
            patch.object(acceptance, "git", return_value=" M tracked.py"),
            patch.object(acceptance, "source_identity") as identity,
        ):
            with self.assertRaises(acceptance.AcceptanceError):
                acceptance.verify_frozen(self.root, {})
            identity.assert_not_called()

    def test_command_timeout_reaps_owned_process_and_never_reports_success(self):
        process = Mock(pid=123)
        process.wait.side_effect = [subprocess.TimeoutExpired("task", 5400), 0]
        process.poll.return_value = None
        stream = io.BytesIO()
        with (
            patch.object(
                acceptance, "process_arguments", return_value=[sys.executable]
            ),
            patch.object(acceptance.subprocess, "Popen", return_value=process),
            patch.object(
                acceptance.subprocess, "run", return_value=Mock(returncode=0)
            ) as cleanup,
            self.assertRaises(acceptance.AcceptanceError),
        ):
            acceptance.run_stage(
                ("task", "setup"), root=self.root, environment={}, stream=stream
            )
        if os.name != "nt":
            process.kill.assert_called_once()
            cleanup.assert_not_called()
        else:
            self.assertEqual(
                cleanup.call_args.args[0], ["taskkill.exe", "/PID", "123", "/T", "/F"]
            )
        self.assertEqual(process.wait.call_count, 2)


@unittest.skipUnless(os.name == "nt", "native Windows PowerShell entry-point contract")
class NativePowerShellTests(unittest.TestCase):
    def test_store_alias_is_refused_before_execution_in_both_native_shells(self):
        script = r"""
function Get-Command {
 [CmdletBinding()]param([string]$Name,[string]$CommandType)
 if($Name -ne 'python.exe' -or $CommandType -ne 'Application'){throw 'Unexpected query.'}
 [pscustomobject]@{Source=$env:TEST_PYTHON_PATH}
}
if($env:TEST_RUN_SETUP -eq '1'){& $env:TEST_WRAPPER -RunSetup}else{& $env:TEST_WRAPPER}
exit $LASTEXITCODE
"""
        with tempfile.TemporaryDirectory(prefix="Store alias kiểm tra ") as temporary:
            root = Path(temporary).resolve()
            wrapper = root / "windows_acceptance.ps1"
            shutil.copyfile(Path(__file__).with_name("windows_acceptance.ps1"), wrapper)
            (root / "task.cmd").write_text(
                '@echo off\r\n@echo forbidden>"%~dp0task-called"\r\n@exit /b 99\r\n',
                encoding="ascii",
            )
            before = sorted(path.name for path in root.iterdir())
            for shell_name in ("powershell.exe", "pwsh.exe"):
                shell = shutil.which(shell_name)
                self.assertIsNotNone(shell)
                for tail, alias in (
                    ("python.exe", True),
                    ("python", True),
                    ("PythonSoftwareFoundation.Python.3.12_package/python.exe", False),
                ):
                    for run_setup in ("0", "1"):
                        environment = {
                            **os.environ,
                            "PATH": str(root) + os.pathsep + os.environ["PATH"],
                            "TEST_WRAPPER": str(wrapper),
                            "TEST_RUN_SETUP": run_setup,
                            "TEST_PYTHON_PATH": str(
                                root / "Microsoft/WindowsApps" / tail
                            ),
                        }
                        result = subprocess.run(
                            [
                                shell,
                                "-NoProfile",
                                "-NonInteractive",
                                "-EncodedCommand",
                                base64.b64encode(script.encode("utf-16-le")).decode(
                                    "ascii"
                                ),
                            ],
                            cwd=root,
                            env=environment,
                            text=True,
                            encoding="utf-8",
                            capture_output=True,
                            timeout=30,
                            check=False,
                        )
                        report = json.loads(result.stdout)
                        self.assertEqual(result.returncode, 2)
                        self.assertEqual(report["acceptance"], "unverified")
                        self.assertEqual(
                            "Store execution alias" in report["reason"], alias
                        )
                        self.assertEqual(
                            sorted(path.name for path in root.iterdir()), before
                        )
                        self.assertFalse((root / "task-called").exists())

    def test_both_native_shells_block_server_before_task_or_project_changes(self):
        metadata = host.host_identity("5.1")
        if metadata["windows11"]:
            self.skipTest(
                "Server refusal contract; Windows 11 acceptance requires explicit operator RunSetup"
            )
        self.assertEqual(
            metadata["product_type"], 3, "This CI contract requires Windows Server"
        )
        with tempfile.TemporaryDirectory(prefix="Windows kiểm tra ") as temporary:
            root = Path(temporary).resolve()
            scripts = copy_collector(root)
            fake_task = root / "task.cmd"
            fake_task.write_text(
                '@echo off\r\n@echo forbidden>"%~dp0task-called"\r\n@exit /b 99\r\n',
                encoding="ascii",
            )
            before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            environment = {
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUTF8": "1",
                "PATH": str(root)
                + os.pathsep
                + os.path.dirname(sys.executable)
                + os.pathsep
                + os.environ["PATH"],
            }
            for name in ("powershell.exe", "pwsh.exe"):
                shell = shutil.which(name)
                self.assertIsNotNone(
                    shell, name + " must be available on the native CI host"
                )
                for mode in ([], ["-RunSetup"]):
                    with self.subTest(shell=name, mode=mode):
                        result = subprocess.run(
                            [
                                shell,
                                "-NoProfile",
                                "-NonInteractive",
                                "-File",
                                str(scripts / "windows_acceptance.ps1"),
                                *mode,
                            ],
                            cwd=root,
                            env=environment,
                            text=True,
                            encoding="utf-8",
                            capture_output=True,
                            timeout=60,
                            check=False,
                        )
                        self.assertEqual(result.returncode, 2, result.stderr)
                        report = json.loads(result.stdout)
                        self.assertEqual(report["status"], "blocked")
                        self.assertEqual(report["acceptance"], "unverified")
                        self.assertFalse(report["host"]["windows11"])
                        self.assertEqual(
                            sorted(
                                str(path.relative_to(root)) for path in root.rglob("*")
                            ),
                            before,
                        )
                        self.assertFalse((root / "task-called").exists())
