import contextlib
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import sync_doctor
from host_tools import HostError


class Registry:
    HKEY_LOCAL_MACHINE = 1
    HKEY_CURRENT_USER = 2
    KEY_WOW64_32KEY = 32
    KEY_WOW64_64KEY = 64
    KEY_READ = 128

    def __init__(self, values):
        self.values = values
        self.seen = []

    def OpenKey(self, hive, path, _reserved, access):
        self.seen.append((hive, path, access))
        key = (hive, access & ~self.KEY_READ)
        if key not in self.values:
            raise FileNotFoundError
        return contextlib.nullcontext(key)

    def QueryValueEx(self, key, name):
        if name != "pv":
            raise AssertionError("Unexpected registry value")
        return (self.values[key], 1)


class SyncDoctorTest(unittest.TestCase):
    def test_lockfile_two_rejects_old_bun_before_other_prerequisites_on_both_platforms(
        self,
    ):
        lockfile = sync_doctor.ROOT / "src/applications/medilab-sync/bun.lock"
        original = lockfile.read_bytes()
        for system in ("Linux", "Windows"):
            with (
                self.subTest(system=system),
                patch.object(sync_doctor.platform, "system", return_value=system),
                patch.object(sync_doctor, "_version", return_value="1.3.2") as version,
                patch.object(sync_doctor, "check_node_version"),
                patch.object(sync_doctor, "check_linux") as linux,
                patch.object(sync_doctor, "check_windows") as windows,
                patch.object(sync_doctor, "link_probe") as link,
                self.assertRaisesRegex(
                    HostError, "Bun 1.3.2 cannot read.*lockfileVersion 2.*Bun >=1.4.0"
                ),
            ):
                sync_doctor.doctor()
            version.assert_called_once_with("bun", ["--version"])
            linux.assert_not_called()
            windows.assert_not_called()
            link.assert_not_called()
        self.assertEqual(lockfile.read_bytes(), original)

    def test_lockfile_two_requires_a_known_compatible_stable_bun(self):
        for version in ("1.4.0", "1.4.4", "1.5.0", "2.0.0"):
            with self.subTest(version=version):
                sync_doctor.check_bun_version(version)
        for version in ("1.3.14", "1.4.0-canary.123", "unknown"):
            with (
                self.subTest(version=version),
                self.assertRaisesRegex(HostError, "Bun >=1.4.0"),
            ):
                sync_doctor.check_bun_version(version)

    def test_unknown_or_missing_lockfile_format_fails_without_rewriting_it(self):
        for content in ('{"lockfileVersion": 3}', '{"workspaces": {}}'):
            with tempfile.TemporaryDirectory(prefix="sync lock ") as directory:
                root = pathlib.Path(directory)
                lockfile = root / "src/applications/medilab-sync/bun.lock"
                lockfile.parent.mkdir(parents=True)
                lockfile.write_text(content, encoding="utf-8")
                with (
                    patch.object(sync_doctor, "ROOT", root),
                    self.assertRaisesRegex(
                        HostError, "Unsupported Sync bun.lock format"
                    ),
                ):
                    sync_doctor.check_bun_version("1.4.4")
                self.assertEqual(lockfile.read_text(encoding="utf-8"), content)

    def test_cachyos_inherits_arch_instructions(self):
        family = sync_doctor.linux_family({"ID": "cachyos", "ID_LIKE": "arch"})
        self.assertEqual(family, "arch")
        message = sync_doctor.linux_instructions(family)
        self.assertIn("pacman", message)
        self.assertIn("webkit2gtk-4.1", message)
        self.assertNotIn("apt", message)

    def test_distribution_guidance_does_not_guess_a_package_manager(self):
        self.assertEqual(sync_doctor.linux_family({"ID": "custom"}), "linux")
        self.assertIn("https://v2.tauri.app", sync_doctor.linux_instructions("linux"))
        self.assertIn("libwebkit2gtk-4.1-dev", sync_doctor.linux_instructions("debian"))
        self.assertIn("webkit2gtk4.1-devel", sync_doctor.linux_instructions("fedora"))

    def test_missing_linux_library_reports_arch_remediation(self):

        def run(argv, **_kwargs):
            return Mock(returncode=1 if argv[-1] == "webkit2gtk-4.1" else 0)

        with (
            patch.object(sync_doctor, "linux_family", return_value="arch"),
            patch.object(sync_doctor.shutil, "which", side_effect=lambda name: name),
            patch.object(sync_doctor, "executable", side_effect=lambda name: name),
            patch.object(sync_doctor, "run", side_effect=run),
            self.assertRaisesRegex(HostError, "webkit2gtk-4.1.*pacman"),
        ):
            sync_doctor.check_linux()

    def test_linux_accepts_either_appindicator_backend(self):
        for available in ("appindicator3-0.1", "ayatana-appindicator3-0.1"):

            def run(argv, expected=available, **_kwargs):
                missing = (
                    argv[-1] in {"appindicator3-0.1", "ayatana-appindicator3-0.1"}
                    and argv[-1] != expected
                )
                return Mock(returncode=int(missing))

            with (
                self.subTest(available=available),
                patch.object(sync_doctor, "linux_family", return_value="arch"),
                patch.object(
                    sync_doctor.shutil, "which", side_effect=lambda name: name
                ),
                patch.object(sync_doctor, "executable", side_effect=lambda name: name),
                patch.object(sync_doctor, "run", side_effect=run),
            ):
                sync_doctor.check_linux()

    def test_windows_rejects_gnu_or_wsl_rust_before_querying_tools(self):
        for host in ("x86_64-pc-windows-gnu", "x86_64-unknown-linux-gnu"):
            with (
                self.subTest(host=host),
                patch.object(sync_doctor, "run") as run,
                self.assertRaisesRegex(HostError, "MSVC"),
            ):
                sync_doctor.check_windows(f"rustc 1.99.1\nhost: {host}\n")
            run.assert_not_called()

    def test_windows_uses_vswhere_and_not_cl_on_powershell_path(self):
        with (
            patch.object(
                sync_doctor.shutil, "which", return_value="C:/Program Files/vswhere.exe"
            ),
            patch.object(
                sync_doctor, "run", return_value=Mock(stdout="C:/Build Tools\n")
            ) as run,
            patch.object(sync_doctor, "webview_version", return_value="140.0.0.1"),
        ):
            sync_doctor.check_windows("host: x86_64-pc-windows-msvc\n")
        self.assertIn(
            "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", run.call_args.args[0]
        )
        self.assertEqual(run.call_args.args[0][0], "C:/Program Files/vswhere.exe")

    def test_windows_finds_cpp_tools_on_the_actual_non_c_drive_with_spaces(self):
        directory = str(
            pathlib.PureWindowsPath("D:/Developer Tools/Program Files (x86)")
        )
        expected = (
            pathlib.Path(directory) / "Microsoft Visual Studio/Installer/vswhere.exe"
        )
        with (
            patch.dict(
                sync_doctor.os.environ, {"PROGRAMFILES(X86)": directory}, clear=True
            ),
            patch.object(sync_doctor.shutil, "which", return_value=None),
            patch.object(
                pathlib.Path,
                "is_file",
                autospec=True,
                side_effect=lambda path: path == expected,
            ),
            patch.object(
                sync_doctor, "run", return_value=Mock(stdout="D:/Developer Tools/VS\n")
            ) as run,
            patch.object(sync_doctor, "webview_version", return_value="140.0.0.1"),
        ):
            sync_doctor.check_windows("host: x86_64-pc-windows-msvc\n")
        self.assertEqual(run.call_args.args[0][0], str(expected))
        self.assertTrue(run.call_args.args[0][0].startswith("D:"))

    def test_missing_windows_paths_fail_without_probing_an_assumed_c_drive(self):
        with (
            patch.dict(sync_doctor.os.environ, {}, clear=True),
            patch.object(sync_doctor.shutil, "which", return_value=None),
            patch.object(
                pathlib.Path,
                "is_file",
                side_effect=AssertionError("An OS path was invented"),
            ) as exists,
            patch.object(sync_doctor, "run") as run,
            self.assertRaisesRegex(HostError, "Windows Program Files variables"),
        ):
            sync_doctor.check_windows("host: x86_64-pc-windows-msvc\n")
        exists.assert_not_called()
        run.assert_not_called()

    def test_windows_arm64_requires_its_native_cpp_component(self):
        with (
            patch.object(sync_doctor.shutil, "which", return_value="vswhere.exe"),
            patch.object(
                sync_doctor, "run", return_value=Mock(stdout="C:/Build Tools\n")
            ) as run,
            patch.object(sync_doctor, "webview_version", return_value="140.0.0.1"),
        ):
            sync_doctor.check_windows("host: aarch64-pc-windows-msvc\n")
        self.assertIn(
            "Microsoft.VisualStudio.Component.VC.Tools.ARM64", run.call_args.args[0]
        )

    def test_windows_requires_installed_tools_and_webview(self):
        with (
            patch.object(sync_doctor.shutil, "which", return_value="vswhere.exe"),
            patch.object(sync_doctor, "run", return_value=Mock(stdout="")),
            self.assertRaisesRegex(HostError, "Build Tools"),
        ):
            sync_doctor.check_windows("host: x86_64-pc-windows-msvc\n")
        with (
            patch.object(sync_doctor.shutil, "which", return_value="vswhere.exe"),
            patch.object(
                sync_doctor, "run", return_value=Mock(stdout="C:/Build Tools")
            ),
            patch.object(sync_doctor, "webview_version", return_value=None),
            self.assertRaisesRegex(HostError, "WebView2"),
        ):
            sync_doctor.check_windows("host: x86_64-pc-windows-msvc\n")

    def test_webview_detection_accepts_machine_or_user_registry_installations(self):
        for hive, view in ((1, 32), (1, 64), (2, 32), (2, 64)):
            registry = Registry({(hive, view): "140.0.1234.5"})
            with self.subTest(hive=hive, view=view):
                self.assertEqual(sync_doctor.webview_version(registry), "140.0.1234.5")
                self.assertTrue(
                    all(
                        (
                            path == sync_doctor.WEBVIEW_CLIENT
                            for _hive, path, _access in registry.seen
                        )
                    )
                )

    def test_zero_or_malformed_webview_version_is_not_readiness(self):
        for value in ("0.0.0.0", "", "installed", 140):
            with self.subTest(value=value):
                self.assertIsNone(
                    sync_doctor.webview_version(Registry({(1, 32): value}))
                )

    def test_disposable_link_probe_is_compiled_without_running_an_application(self):
        observed = []

        def run(argv, **kwargs):
            observed.append(argv)
            self.assertEqual(
                pathlib.Path(argv[1]).read_text(encoding="utf-8"), "fn main() {}\n"
            )
            self.assertEqual(kwargs["timeout"], 60)
            return Mock(returncode=0)

        with (
            patch.object(sync_doctor, "executable", return_value="rustc"),
            patch.object(sync_doctor, "run", side_effect=run),
        ):
            sync_doctor.link_probe()
        self.assertEqual(len(observed), 1)
        self.assertFalse(
            pathlib.Path(observed[0][1]).exists(),
            "temporary probe directory is removed",
        )

    def test_linker_or_sdk_failure_is_actionable_and_redacted(self):
        with (
            patch.object(sync_doctor, "executable", return_value="rustc"),
            patch.object(
                sync_doctor,
                "run",
                return_value=Mock(returncode=1, stderr="FAKE-PRIVATE-ENV"),
            ),
            self.assertRaisesRegex(HostError, "SDK") as failure,
        ):
            sync_doctor.link_probe()
        self.assertNotIn("FAKE-PRIVATE-ENV", str(failure.exception))

    def test_gui_checks_are_separate_from_compiler_readiness(self):
        with (
            patch.object(sync_doctor.platform, "system", return_value="Linux"),
            patch.dict(sync_doctor.os.environ, {}, clear=True),
            self.assertRaisesRegex(HostError, "graphical"),
        ):
            sync_doctor.check_gui()
        with (
            patch.object(sync_doctor.platform, "system", return_value="Linux"),
            patch.dict(sync_doctor.os.environ, {"DISPLAY": ":99"}, clear=True),
            self.assertRaisesRegex(HostError, "D-Bus"),
        ):
            sync_doctor.check_gui()

    def test_missing_cargo_or_components_never_becomes_a_skipped_success(self):
        with (
            patch.object(sync_doctor, "executable", side_effect=HostError("missing")),
            self.assertRaisesRegex(HostError, "rustup"),
        ):
            sync_doctor._version("cargo", ["--version"])
        with (
            patch.object(sync_doctor, "executable", return_value="cargo"),
            patch.object(
                sync_doctor,
                "run",
                side_effect=subprocess.CalledProcessError(1, ["cargo", "fmt"]),
            ),
            self.assertRaisesRegex(HostError, "rustfmt/clippy"),
        ):
            sync_doctor._version("cargo", ["fmt", "--version"])

    def test_standalone_doctor_uses_the_shared_vite_node_range_before_native_checks(
        self,
    ):
        for version, allowed in (
            ("v20.19.0", True),
            ("v22.12.0", True),
            ("v23.0.0", True),
            ("v20.18.0", False),
            ("v22.11.0", False),
            ("v21.7.0", False),
        ):

            def tool(name, _arguments, node=version):
                return (
                    node
                    if name == "node"
                    else "1.4.0"
                    if name == "bun"
                    else "native fixture tool"
                )

            with (
                self.subTest(version=version),
                patch.object(sync_doctor.platform, "system", return_value="Linux"),
                patch.object(sync_doctor, "_version", side_effect=tool),
                patch.object(sync_doctor, "check_linux") as native,
                patch.object(sync_doctor, "link_probe") as link,
            ):
                if allowed:
                    self.assertEqual(sync_doctor.doctor()["Node"], version)
                    native.assert_called_once()
                    link.assert_called_once()
                else:
                    with self.assertRaisesRegex(HostError, "Vite"):
                        sync_doctor.doctor()
                    native.assert_not_called()
                    link.assert_not_called()


if __name__ == "__main__":
    unittest.main()
