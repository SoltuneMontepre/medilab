"""Reserve the Docker proof's single owned report destination."""

import base64
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

from onlyoffice_state import protect

OWNER_CHECK = r"""
$ErrorActionPreference='Stop'
Import-Module -Name (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
$user=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$owner=(Get-Acl -LiteralPath $env:MEDILAB_REPORT_OWNER_PATH).GetOwner([Security.Principal.SecurityIdentifier]).Value
if($owner -ne $user){exit 1}
"""


class FixedReport:
    def __init__(self, root, requested):
        self.root = Path(root)
        self.path = self.root / ".local" / "onlyoffice-docker-network.json"
        requested = Path(requested)
        if ".." in requested.parts or os.path.normcase(
            os.path.abspath(requested)
        ) != os.path.normcase(str(self.path)):
            raise RuntimeError(
                "The Docker proof accepts only its fixed local report destination."
            )
        self.validate()
        try:
            self.path.parent.mkdir(mode=0o700)
        except FileExistsError:
            pass
        else:
            protect(self.path.parent)
        self.validate()

    @staticmethod
    def owned(path, metadata):
        if os.name == "nt":
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-EncodedCommand",
                    base64.b64encode(OWNER_CHECK.encode("utf-16-le")).decode("ascii"),
                ],
                env=dict(os.environ, MEDILAB_REPORT_OWNER_PATH=str(path)),
                capture_output=True,
                check=False,
                timeout=30,
            )
            if result.returncode:
                raise RuntimeError(
                    "The Docker proof report requires current-user ownership."
                )
        elif metadata.st_uid != os.getuid():
            raise RuntimeError(
                "The Docker proof report requires current-user ownership."
            )

    def validate(self):
        for path in (
            *reversed(self.root.parents),
            self.root,
            self.path.parent,
            self.path,
        ):
            try:
                metadata = path.lstat()
            except FileNotFoundError:
                if path not in (self.path.parent, self.path):
                    raise RuntimeError(
                        "The Docker proof report directory is unavailable."
                    ) from None
                continue
            if stat.S_ISLNK(metadata.st_mode) or path.is_junction():
                raise RuntimeError("The Docker proof report refuses linked paths.")
            expected_type = stat.S_ISREG if path == self.path else stat.S_ISDIR
            if not expected_type(metadata.st_mode):
                raise RuntimeError(
                    "The Docker proof report requires ordinary directories and a regular file."
                )
            if path in (self.root, self.path.parent, self.path):
                self.owned(path, metadata)

    def write(self, report):
        self.validate()
        descriptor, temporary = tempfile.mkstemp(
            prefix=".onlyoffice-network-report-", dir=self.path.parent
        )
        temporary = Path(temporary)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(report, stream, sort_keys=True, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            protect(temporary)
            self.validate()
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
