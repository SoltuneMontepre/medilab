"""Integrity of checkout-local state paths; callers supply a trusted checkout root.

The checkout is trusted executable code. Its .local subtree must remain owned and
unwritable by other users before private files are opened. OS administrators are
already trusted on Windows; this check grants them no additional permissions.
"""

import argparse
import base64
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

ERROR = "Local state path integrity cannot be verified; preserve data and review owner/write permissions."
WINDOWS_ACL = r"""
$ErrorActionPreference='Stop'
Import-Module -Name (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
$p=$env:MEDILAB_ONLYOFFICE_ACL_PATH
$u=[Security.Principal.WindowsIdentity]::GetCurrent().User
if($env:MEDILAB_ONLYOFFICE_ACL_PROTECT -eq '1') {
  if(Test-Path -LiteralPath $p -PathType Container) {
    $a=New-Object Security.AccessControl.DirectorySecurity
    $flags=[Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'
  } else {
    $a=New-Object Security.AccessControl.FileSecurity
    $flags=[Security.AccessControl.InheritanceFlags]::None
  }
  $a.SetOwner($u)
  $a.SetAccessRuleProtection($true,$false)
  foreach($sid in @($u.Value,'S-1-5-18')) {
    $identity=New-Object Security.Principal.SecurityIdentifier($sid)
    $rule=New-Object Security.AccessControl.FileSystemAccessRule($identity,'FullControl',$flags,'None','Allow')
    $a.AddAccessRule($rule)
  }
  Set-Acl -LiteralPath $p -AclObject $a
}
$a=Get-Acl -LiteralPath $p
if(-not $a.AreAccessRulesProtected){exit 1}
if($a.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $u.Value){exit 1}
foreach($rule in $a.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])) {
  if($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Value -notin @($u.Value,'S-1-5-18')) {exit 1}
}
"""
WINDOWS_ANCESTORS = r"""
$ErrorActionPreference='Stop'
Import-Module -Name (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
$u=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$trusted=@($u,'S-1-5-18','S-1-5-32-544')
$mutation=2 -bor 4 -bor 16 -bor 64 -bor 256 -bor 65536 -bor 262144 -bor 524288 -bor 0x40000000 -bor 0x10000000
foreach($p in (ConvertFrom-Json $env:MEDILAB_LOCAL_STATE_PATHS)) {
  $a=Get-Acl -LiteralPath $p
  if($a.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $trusted){exit 1}
  foreach($r in $a.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])) {
    if($r.AccessControlType -eq 'Allow' -and
       ($r.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -eq 0 -and
       $r.IdentityReference.Value -notin $trusted -and
       ([int64]$r.FileSystemRights -band $mutation) -ne 0){exit 1}
  }
}
"""


class LocalPrivatePathError(RuntimeError):
    pass


def _powershell(script, environment, *, invoke=None):
    try:
        result = (invoke or subprocess.run)(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-EncodedCommand",
                base64.b64encode(script.encode("utf-16-le")).decode("ascii"),
            ],
            env=environment,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise LocalPrivatePathError(ERROR) from None
    if result.returncode:
        raise LocalPrivatePathError(ERROR)


def windows_private_acl(path, *, create=False, invoke=None):
    _powershell(
        WINDOWS_ACL,
        dict(
            os.environ,
            MEDILAB_ONLYOFFICE_ACL_PATH=str(path),
            MEDILAB_ONLYOFFICE_ACL_PROTECT="1" if create else "0",
        ),
        invoke=invoke,
    )


def _scoped_path(root, path):
    root, path = Path(root), Path(path)
    if not root.is_absolute() or not path.is_absolute() or ".." in path.parts:
        raise LocalPrivatePathError(ERROR)
    root = Path(os.path.abspath(root))
    path = Path(os.path.abspath(path))
    base = root / ".local"
    try:
        relative = path.relative_to(base)
    except ValueError:
        raise LocalPrivatePathError(ERROR) from None
    return path, [
        base,
        *(
            base.joinpath(*relative.parts[:index])
            for index in range(1, len(relative.parts) + 1)
        ),
    ]


def _check_existing_item(item, info, leaf):
    if stat.S_ISLNK(info.st_mode) or (
        hasattr(item, "is_junction") and item.is_junction()
    ):
        raise LocalPrivatePathError(ERROR)
    if not stat.S_ISDIR(info.st_mode) and (not leaf or not stat.S_ISREG(info.st_mode)):
        raise LocalPrivatePathError(ERROR)
    if os.name != "nt" and (
        info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022
    ):
        raise LocalPrivatePathError(ERROR)


def guard_local_path(root, path):
    path, chain = _scoped_path(root, path)
    existing = []
    try:
        for index, item in enumerate(chain):
            try:
                info = item.lstat()
            except FileNotFoundError:
                break
            _check_existing_item(item, info, index == len(chain) - 1)
            existing.append(str(item))
        if os.name == "nt" and existing:
            _powershell(
                WINDOWS_ANCESTORS,
                dict(os.environ, MEDILAB_LOCAL_STATE_PATHS=json.dumps(existing)),
            )
    except OSError:
        raise LocalPrivatePathError(ERROR) from None
    return path


def protect_created_path(root, path):
    path, _chain = _scoped_path(root, path)
    if path.parent != Path(root):
        guard_local_path(root, path.parent)
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or (
            hasattr(path, "is_junction") and path.is_junction()
        ):
            raise LocalPrivatePathError(ERROR)
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise LocalPrivatePathError(ERROR)
        if os.name == "nt":
            windows_private_acl(path, create=True)
        elif info.st_uid == os.getuid():
            path.chmod(0o700 if stat.S_ISDIR(info.st_mode) else 0o600)
        else:
            raise LocalPrivatePathError(ERROR)
    except OSError:
        raise LocalPrivatePathError(ERROR) from None


def ensure_local_directory(root, path):
    path, chain = _scoped_path(root, path)
    guard_local_path(root, path)
    try:
        for item in chain:
            try:
                item.mkdir(mode=0o700)
            except FileExistsError:
                guard_local_path(root, item)
                if not item.is_dir():
                    raise LocalPrivatePathError(ERROR)
            else:
                protect_created_path(root, item)
        return guard_local_path(root, path)
    except OSError:
        raise LocalPrivatePathError(ERROR) from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument("directory", type=Path)
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    try:
        ensure_local_directory(root, root / arguments.directory)
    except LocalPrivatePathError as error:
        sys.stderr.write(f"{error}\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
