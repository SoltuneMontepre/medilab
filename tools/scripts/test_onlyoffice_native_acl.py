"""Exercise the actual Windows ACL helper using harmless private test objects."""

import base64
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import onlyoffice_state as state


def diagnostic_script():
    stages = {
        "Import-Module": "import-native-security",
        "$u=": "identity",
        "$a=New-Object": "security-descriptor",
        "$a.SetOwner": "owner",
        "$a.SetAccessRuleProtection": "protection",
        "$identity=": "rule-identity",
        "$rule=": "rule",
        "$a.AddAccessRule": "add-rule",
        "Set-Acl": "set-acl",
        "$a=Get-Acl": "read-acl",
        "if(-not $a.AreAccessRulesProtected)": "verify-protection",
        "if($a.GetOwner": "verify-owner",
        "foreach($rule": "verify-rules",
    }
    lines = ["$stage='start'", "try {"]
    for line in state.WINDOWS_ACL.splitlines():
        for prefix, stage in stages.items():
            if line.strip().startswith(prefix):
                lines.append(f"$stage='{stage}'")
                break
        lines.append(line.replace("exit 1", "throw 'Synthetic ACL validation failed'"))
    lines.extend(
        [
            "} catch {",
            "$detail=@{stage=$stage;type=$_.Exception.GetType().FullName;id=$_.FullyQualifiedErrorId}",
            "[Console]::Error.WriteLine(($detail | ConvertTo-Json -Compress))",
            "exit 91",
            "}",
        ]
    )
    return "\n".join(lines)


@unittest.skipUnless(os.name == "nt", "native Windows private-ACL security contract")
class NativeWindowsAclTest(unittest.TestCase):
    def test_private_directory_and_file_protection_and_unsafe_rule_refusal(self):
        invoke = subprocess.run
        with tempfile.TemporaryDirectory(prefix="ACL kiểm tra ") as temporary:
            directory = Path(temporary) / "synthetic private directory"
            directory.mkdir()
            file = directory / "harmless-marker.txt"
            file.write_text(
                "Synthetic test data; contains no credential.\n", encoding="utf-8"
            )
            for target in (directory, file):
                for create in (True, False):
                    calls = []

                    def capture(*args, _calls=calls, **kwargs):
                        result = invoke(*args, **kwargs)
                        _calls.append((result, kwargs["env"]))
                        return result

                    with patch.object(state.subprocess, "run", side_effect=capture):
                        try:
                            state.windows_acl(target, create=create)
                        except state.OnlyofficeError:
                            diagnostic = invoke(
                                [
                                    "powershell.exe",
                                    "-NoProfile",
                                    "-NonInteractive",
                                    "-EncodedCommand",
                                    base64.b64encode(
                                        diagnostic_script().encode("utf-16-le")
                                    ).decode("ascii"),
                                ],
                                env=calls[-1][1],
                                capture_output=True,
                                check=False,
                            )
                            self.fail(
                                f"Synthetic native ACL phase={'protect' if create else 'verify'} "
                                f"kind={'directory' if target == directory else 'file'} "
                                f"exit={calls[-1][0].returncode}; "
                                f"typed diagnostic={diagnostic.stderr.decode('utf-8', errors='replace')}; "
                                f"original synthetic stderr={calls[-1][0].stderr.decode('utf-8', errors='replace')}"
                            )
            environment = calls[-1][1]
            widen = (
                state.WINDOWS_ACL
                + """
$ErrorActionPreference='Stop'
$p=$env:MEDILAB_ONLYOFFICE_ACL_PATH
$a=Get-Acl -LiteralPath $p
$identity=New-Object Security.Principal.SecurityIdentifier('S-1-1-0')
$rule=New-Object Security.AccessControl.FileSystemAccessRule($identity,'Read','Allow')
$a.AddAccessRule($rule)
Set-Acl -LiteralPath $p -AclObject $a
"""
            )
            result = invoke(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-EncodedCommand",
                    base64.b64encode(widen.encode("utf-16-le")).decode("ascii"),
                ],
                env=environment,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                result.returncode,
                0,
                "Synthetic unsafe-rule fixture could not be prepared.",
            )
            with self.assertRaises(state.OnlyofficeError):
                state.windows_acl(file)
            state.windows_acl(file, create=True)
            state.windows_acl(file)


if __name__ == "__main__":
    unittest.main()
