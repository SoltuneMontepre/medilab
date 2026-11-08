"""Private path checks use only owned temporary trees and synthetic Windows ACLs."""

import io
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

import local_private_paths as private

MODIFY = "0x1301bf"
PRIVATE_ACES = "(A;OICI;FA;;;USER)(A;OICI;FA;;;SY)"


class LocalPrivatePathsTest(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "POSIX umask contract")
    def test_command_creates_private_ancestors_with_a_permissive_umask(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            previous = os.umask(0o002)
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        private.__file__,
                        "--root",
                        str(root),
                        ".local/coverage",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            finally:
                os.umask(previous)
            self.assertEqual(result.returncode, 0, result.stderr)
            for path in (root / ".local", root / ".local/coverage"):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="private paths kiểm tra ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.directory = private.ensure_local_directory(
            self.root, self.root / ".local/project/generation"
        )

    def test_existing_safe_chain_and_absent_leaf_are_readonly(self):
        file = self.directory / "state.json"
        before = [
            (item, item.stat().st_mode, item.stat().st_mtime_ns)
            for item in (self.root / ".local", self.directory.parent, self.directory)
        ]
        self.assertEqual(private.guard_local_path(self.root, file), file)
        self.assertFalse(file.exists())
        self.assertEqual(
            before,
            [
                (item, item.stat().st_mode, item.stat().st_mtime_ns)
                for item, _mode, _mtime in before
            ],
        )

    def test_foreign_and_traversal_paths_fail_before_filesystem_access(self):
        for path in (
            self.root / "outside/state.json",
            self.root / ".local/../outside/state.json",
        ):
            with self.subTest(path=path.name), patch.object(Path, "lstat") as probe:
                with self.assertRaises(private.LocalPrivatePathError):
                    private.guard_local_path(self.root, path)
                probe.assert_not_called()

    @unittest.skipIf(os.name == "nt", "POSIX owner and mode policy")
    def test_mutable_ancestor_rejected_for_existing_and_absent_leaf_without_repair(
        self,
    ):
        leaf = self.directory / "state.json"
        leaf.write_text("private-marker", encoding="utf-8")
        private.protect_created_path(self.root, leaf)
        for ancestor in (self.root / ".local", self.directory.parent):
            for mode in (0o775, 0o777):
                ancestor.chmod(mode)
                try:
                    for target in (leaf, self.directory / "missing/leaf.json"):
                        with self.subTest(mode=oct(mode), target=target.name):
                            with self.assertRaises(private.LocalPrivatePathError):
                                private.guard_local_path(self.root, target)
                            with self.assertRaises(private.LocalPrivatePathError):
                                private.ensure_local_directory(self.root, target.parent)
                            self.assertEqual(
                                stat.S_IMODE(ancestor.stat().st_mode), mode
                            )
                            self.assertEqual(leaf.read_text(), "private-marker")
                finally:
                    ancestor.chmod(0o700)

    @unittest.skipIf(os.name == "nt", "POSIX owner and mode policy")
    def test_creation_uses_private_modes_with_permissive_umask(self):
        target = self.root / ".local/new/project/generation"
        previous = os.umask(0)
        try:
            private.ensure_local_directory(self.root, target)
        finally:
            os.umask(previous)
        for item in (target, target.parent, target.parent.parent):
            self.assertEqual(stat.S_IMODE(item.stat().st_mode), 0o700)

    @unittest.skipIf(os.name == "nt", "POSIX owner and mode policy")
    def test_foreign_owner_refused_without_chmod(self):
        actual = Path.lstat

        def foreign(path):
            result = actual(path)
            if path == self.directory.parent:
                values = list(result)
                values[4] = os.getuid() + 1
                return os.stat_result(values)
            return result

        with (
            patch.object(Path, "lstat", foreign),
            patch.object(Path, "chmod") as repair,
        ):
            with self.assertRaises(private.LocalPrivatePathError):
                private.guard_local_path(self.root, self.directory / "missing")
            repair.assert_not_called()

    @unittest.skipIf(
        os.name == "nt",
        "Native links tested where symlink creation requires no extra privilege",
    )
    def test_link_and_non_directory_ancestor_refused_without_following(self):
        link = self.root / ".local/link"
        link.symlink_to(self.directory, target_is_directory=True)
        with self.assertRaises(private.LocalPrivatePathError):
            private.guard_local_path(self.root, link / "absent")
        file = self.directory / "file"
        file.write_text("marker")
        with self.assertRaises(private.LocalPrivatePathError):
            private.guard_local_path(self.root, file / "absent")

    @unittest.skipUnless(os.name == "nt", "Native Windows ACL policy")
    def test_native_ancestor_mutation_aces_and_strict_private_leaf(self):
        ancestor = self.directory.parent
        script = r"""
$ErrorActionPreference='Stop'
Import-Module -Name (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
$p=$env:MEDILAB_ONLYOFFICE_ACL_PATH
$i=Get-Item -LiteralPath $p -Force
$a=$i.GetAccessControl('Access')
$id=New-Object Security.Principal.SecurityIdentifier($env:TEST_ACL_SID)
$r=New-Object Security.AccessControl.FileSystemAccessRule($id,$env:TEST_ACL_RIGHT,'None','None','Allow')
$a.AddAccessRule($r)
$i.SetAccessControl($a)
"""
        for sid, right, allowed in (
            ("S-1-5-32-545", "ReadAndExecute", True),
            ("S-1-5-32-544", "FullControl", True),
            ("S-1-3-4", "FullControl", True),
            ("S-1-5-32-545", "WriteData", False),
            ("S-1-5-32-545", "ChangePermissions", False),
            ("S-1-5-32-545", "TakeOwnership", False),
        ):
            with self.subTest(sid=sid, right=right):
                private.windows_private_acl(ancestor, create=True)
                private._powershell(
                    script,
                    dict(
                        os.environ,
                        MEDILAB_ONLYOFFICE_ACL_PATH=str(ancestor),
                        TEST_ACL_SID=sid,
                        TEST_ACL_RIGHT=right,
                    ),
                )
                try:
                    if allowed:
                        private.guard_local_path(self.root, self.directory / "absent")
                    else:
                        with self.assertRaises(private.LocalPrivatePathError):
                            private.guard_local_path(
                                self.root, self.directory / "absent"
                            )
                    with self.assertRaises(private.LocalPrivatePathError):
                        private.windows_private_acl(ancestor)
                finally:
                    private.windows_private_acl(ancestor, create=True)

    def _windows_sddl(self, path, sddl=None):
        script = r"""
$ErrorActionPreference='Stop'
$u=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$i=Get-Item -LiteralPath $env:TEST_ACL_PATH -Force
$a=$i.GetAccessControl('Access')
if($env:TEST_ACL_SDDL) {
  $a.SetSecurityDescriptorSddlForm($env:TEST_ACL_SDDL.Replace('USER',$u),'Access')
  $i.SetAccessControl($a)
  $a=$i.GetAccessControl('Access')
}
[Console]::Out.Write($a.GetSecurityDescriptorSddlForm('Access'))
"""
        environment = dict(os.environ, TEST_ACL_PATH=str(path), TEST_ACL_SDDL=sddl or "")
        return private._powershell(script, environment).decode("ascii")

    def _private_aces(self):
        script = r"""
$u=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$d=New-Object Security.AccessControl.RawSecurityDescriptor($env:TEST_ACL_SDDL.Replace('USER',$u))
[Console]::Out.Write($d.GetSddlForm('Access'))
"""
        environment = dict(os.environ, TEST_ACL_SDDL=f"D:P{PRIVATE_ACES}")
        sddl = private._powershell(script, environment).decode("ascii")
        return sorted(sddl.removeprefix("D:P(").removesuffix(")").split(")("))

    def _inheriting_root(self):
        temporary = tempfile.TemporaryDirectory(prefix="inherited kiểm tra ")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        self._windows_sddl(root, f"D:P(A;OICI;FA;;;SY)(A;OICI;{MODIFY};;;AU)")
        (root / ".local/project").mkdir(parents=True)
        return root

    @unittest.skipUnless(os.name == "nt", "Native Windows ACL repair")
    def test_inherited_writers_repaired_once_to_current_user_and_system(self):
        root = self._inheriting_root()
        local = root / ".local"
        target = local / "project/generation"
        output = io.StringIO()
        with redirect_stderr(output):
            self.assertEqual(private.ensure_local_directory(root, target), target)
        self.assertEqual(
            output.getvalue().splitlines(),
            [private.REPAIRED.format(path=local)],
        )
        sddl = self._windows_sddl(local)
        self.assertTrue(sddl.startswith("D:PAI("), sddl)
        self.assertEqual(
            sorted(sddl.removeprefix("D:PAI(").removesuffix(")").split(")(")),
            self._private_aces(),
        )
        self.assertNotIn(";AU)", self._windows_sddl(local / "project"))
        output = io.StringIO()
        with redirect_stderr(output):
            private.guard_local_path(root, target / "state.json")
        self.assertEqual(output.getvalue(), "")

    @unittest.skipUnless(os.name == "nt", "Native Windows ACL repair")
    def test_explicit_writer_refused_without_repair(self):
        root = self._inheriting_root()
        local = root / ".local"
        self._windows_sddl(local, f"D:(A;OICI;{MODIFY};;;BU)")
        before = self._windows_sddl(local)
        self.assertIn(";;;AU)", before)
        for call in (private.guard_local_path, private.ensure_local_directory):
            with self.subTest(call=call.__name__):
                with self.assertRaises(private.LocalPrivatePathError):
                    call(root, local / "project/absent")
        self.assertEqual(before, self._windows_sddl(local))

    @unittest.skipUnless(os.name == "nt", "Native Windows ACL repair")
    def test_file_with_inherited_writer_refused_without_repair(self):
        file = self.directory / "state.json"
        file.write_text("private-marker", encoding="utf-8")
        self._windows_sddl(
            self.directory, f"D:P{PRIVATE_ACES}(A;OIIO;{MODIFY};;;BU)"
        )
        before = self._windows_sddl(file)
        self.assertIn(f"(A;ID;{MODIFY};;;BU)", before)
        with self.assertRaises(private.LocalPrivatePathError):
            private.guard_local_path(self.root, file)
        self.assertEqual(before, self._windows_sddl(file))
        private.guard_local_path(self.root, self.directory / "absent")

    @unittest.skipUnless(os.name == "nt", "Native Windows ACL repair")
    def test_foreign_owner_refused_without_repair(self):
        root = self._inheriting_root()
        local = root / ".local"
        result = subprocess.run(
            ["icacls", str(local), "/setowner", "*S-1-5-32-544"],
            capture_output=True,
            check=False,
        )
        if result.returncode:
            self.skipTest("Setting another owner needs an elevated token")
        before = self._windows_sddl(local)
        with self.assertRaises(private.LocalPrivatePathError):
            private.ensure_local_directory(root, local / "project")
        self.assertEqual(before, self._windows_sddl(local))

    @unittest.skipUnless(os.name == "nt", "Native Windows junctions")
    def test_junction_with_inherited_writers_refused_without_repair(self):
        root = self._inheriting_root()
        outside = root / "outside"
        outside.mkdir()
        junction = root / ".local/project/link"
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
            capture_output=True,
            check=True,
        )
        before = self._windows_sddl(outside)
        with self.assertRaises(private.LocalPrivatePathError):
            private.ensure_local_directory(root, junction / "absent")
        self.assertEqual(before, self._windows_sddl(outside))

    @unittest.skipUnless(os.name == "nt", "Windows ancestor backend")
    def test_repair_is_reported_once_per_repaired_path(self):
        backend = subprocess.CompletedProcess([], 0, stdout=b"0\r\n", stderr=b"")
        output = io.StringIO()
        with (
            patch.object(private.subprocess, "run", return_value=backend),
            redirect_stderr(output),
        ):
            private.guard_local_path(self.root, self.directory / "absent")
        self.assertEqual(
            output.getvalue(),
            private.REPAIRED.format(path=self.root / ".local") + "\n",
        )

    @unittest.skipUnless(os.name == "nt", "Windows ancestor backend")
    def test_unexpected_repair_output_refused(self):
        for stdout in (b"7", b"repaired"):
            backend = subprocess.CompletedProcess([], 0, stdout=stdout, stderr=b"")
            with (
                self.subTest(stdout=stdout),
                patch.object(private.subprocess, "run", return_value=backend),
                self.assertRaises(private.LocalPrivatePathError),
            ):
                private.guard_local_path(self.root, self.directory / "absent")

    def test_windows_error_is_generic_and_never_echoes_backend_output(self):
        backend = subprocess.CompletedProcess(
            [], 1, stdout=b"private-marker", stderr=b"private-marker"
        )
        with (
            patch.object(private.subprocess, "run", return_value=backend),
            self.assertRaises(private.LocalPrivatePathError) as caught,
        ):
            private.windows_private_acl(self.directory)
        self.assertNotIn("private-marker", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

    @unittest.skipUnless(os.name == "nt", "Native Windows raw SDDL policy")
    def test_native_generic_write_and_all_refused_but_read_control_allowed(self):
        ancestor = self.directory.parent
        script = r"""
$ErrorActionPreference='Stop'
Import-Module -Name (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
$p=$env:MEDILAB_ONLYOFFICE_ACL_PATH
$u=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$i=Get-Item -LiteralPath $p -Force
$a=$i.GetAccessControl('Access')
$sddl="D:P(A;;FA;;;$u)(A;;FA;;;SY)(A;;$($env:TEST_ACL_SDDL_RIGHT);;;BU)"
$a.SetSecurityDescriptorSddlForm($sddl,[Security.AccessControl.AccessControlSections]::Access)
$i.SetAccessControl($a)
"""
        for right, allowed in (
            ("GW", False),
            ("GA", False),
            ("GR", True),
            ("RC", True),
        ):
            with self.subTest(right=right):
                private.windows_private_acl(ancestor, create=True)
                private._powershell(
                    script,
                    dict(
                        os.environ,
                        MEDILAB_ONLYOFFICE_ACL_PATH=str(ancestor),
                        TEST_ACL_SDDL_RIGHT=right,
                    ),
                )
                try:
                    if allowed:
                        private.guard_local_path(self.root, self.directory / "absent")
                    else:
                        with self.assertRaises(private.LocalPrivatePathError):
                            private.guard_local_path(
                                self.root, self.directory / "absent"
                            )
                    with self.assertRaises(private.LocalPrivatePathError):
                        private.windows_private_acl(ancestor)
                finally:
                    private.windows_private_acl(ancestor, create=True)

    def test_windows_acl_timeout_is_bounded_and_error_redacted(self):
        secret = "synthetic-private-command-value"
        timeout = subprocess.TimeoutExpired(
            ["powershell.exe", secret], 30, output=secret, stderr=secret
        )
        with (
            patch.object(private.subprocess, "run", side_effect=timeout) as run,
            self.assertRaises(private.LocalPrivatePathError) as caught,
        ):
            private.windows_private_acl(self.directory)
        self.assertEqual(run.call_args.kwargs["timeout"], 30)
        self.assertEqual(str(caught.exception), private.ERROR)
        self.assertNotIn(secret, repr(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)


if __name__ == "__main__":
    unittest.main()
