"""Read native Windows host metadata without initializing a project or opening the desktop app."""

import base64
import json
import platform
import re
import sys

import demo_bootstrap as bootstrap
import local_setup
from host_tools import HostError, assert_onlyoffice_engine, executable, run

CIM_QUERY = r"""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
$os=Get-CimInstance -ClassName Win32_OperatingSystem
[pscustomobject]@{
 caption=$os.Caption
 build=[int]$os.BuildNumber
 product_type=[int]$os.ProductType
 architecture=$os.OSArchitecture
}|ConvertTo-Json -Compress
"""
SYNC_DOCTOR = (
    "import json,sys;sys.dont_write_bytecode=True;"
    "sys.path.insert(0,'tools/scripts');"
    "from sync_doctor import doctor;"
    "print(json.dumps(doctor(link=False)))"
)


def host_identity(shell_version):
    identity = {
        "system": platform.system(),
        "powershell_version": shell_version,
        "windows11": False,
    }
    if identity["system"] != "Windows":
        return identity
    if not re.fullmatch(r"(?:5\.1|7\.\d+)(?:\.\d+){0,2}", shell_version):
        raise HostError("Use native Windows PowerShell 5.1 or PowerShell 7.")
    query = base64.b64encode(CIM_QUERY.encode("utf-16-le")).decode("ascii")
    result = run(
        [
            executable("powershell.exe"),
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            query,
        ],
        env=local_setup.host_environment(),
        capture_output=True,
        timeout=30,
    )
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        raise HostError(
            "Native Windows operating-system metadata could not be verified."
        )
    caption, build, product_type = (
        data.get("caption"),
        data.get("build"),
        data.get("product_type"),
    )
    if (
        not isinstance(caption, str)
        or type(build) is not int
        or type(product_type) is not int
    ):
        raise HostError(
            "Native Windows operating-system metadata could not be verified."
        )
    identity.update(
        caption=caption,
        build=build,
        product_type=product_type,
        architecture=data.get("architecture"),
        windows11=product_type == 1
        and build >= 22000
        and bool(re.search(r"\bWindows 11\b", caption)),
    )
    return identity


def prerequisite_inventory(root):
    environment = local_setup.host_environment()
    environment["RUSTUP_AUTO_INSTALL"] = "0"
    versions = {}
    for tool in ("python", "git", "task", "uv", "node", "npx", "bun"):
        result = run(
            [executable(tool), "--version"],
            env=environment,
            capture_output=True,
            timeout=20,
        )
        version = re.search(r"(?<!\d)\d+\.\d+(?:\.\d+){0,2}", result.stdout)
        if not version:
            raise HostError(
                "A required native tool did not return a recognizable version."
            )
        versions[tool] = version[0]
    if tuple(map(int, versions["python"].split(".")[:2])) < (3, 12):
        raise HostError("The native python command must select Python 3.12 or newer.")
    bootstrap._assert_local_engine()
    engine = json.loads(
        run(
            ["docker", "info", "--format", "{{json .}}"],
            env=environment,
            capture_output=True,
            timeout=30,
        ).stdout
    )
    local_setup.check_engine_transport(engine)
    assert_onlyoffice_engine(engine)
    resources = local_setup.engine_information(engine)
    local_setup.check_engine_resources(resources)
    compose = run(
        ["docker", "compose", "version", "--short"],
        env=environment,
        capture_output=True,
        timeout=30,
    )
    local_setup.check_compose_version(compose.stdout)
    native = json.loads(
        run(
            [sys.executable, "-B", "-c", SYNC_DOCTOR],
            cwd=root,
            env=environment,
            capture_output=True,
            timeout=120,
        ).stdout
    )
    return {
        "versions": versions,
        "native_sync": native,
        "engine": {
            "provider": "podman" if "host" in engine else "docker",
            "server_version": engine.get("ServerVersion")
            or engine.get("version", {}).get("Version"),
            **resources,
        },
    }
