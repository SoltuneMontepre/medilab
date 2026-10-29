"""Set up the selected Odoo, ONLYOFFICE and native Sync development environment."""

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import demo_bootstrap as bootstrap
from compose_env import project_name
from host_tools import HostError, check_node_version, executable, run

ROOT = Path(__file__).resolve().parents[2]
MIN_ENGINE_MEMORY = 8 * 1024**3
MIN_PYTHON = (3, 12)
TOOL_ENVIRONMENT = (
    "APPDATA",
    "LOCALAPPDATA",
    "CARGO_HOME",
    "CARGO_BUILD_JOBS",
    "RUSTUP_HOME",
    "RUSTUP_TOOLCHAIN",
    "BUN_INSTALL",
    "UV_CACHE_DIR",
    "UV_PYTHON_INSTALL_DIR",
    "UV_PYTHON",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
)
HOST_ENVIRONMENT = (
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "PROGRAMW6432",
    "PROGRAMDATA",
    "ALLUSERSPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "PATH",
    "PATHEXT",
    "HOME",
    "USERPROFILE",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DOCKER_CONFIG",
    "CONTAINER_HOST",
    "CONTAINER_CONNECTION",
    "XDG_RUNTIME_DIR",
    "SSL_CERT_FILE",
    "NODE_EXTRA_CA_CERTS",
    "NO_COLOR",
    "FORCE_COLOR",
    "TERM",
)


def host_environment():
    return {
        key: value
        for key, value in os.environ.items()
        if key in (*HOST_ENVIRONMENT, *TOOL_ENVIRONMENT)
    }


def engine_information(document):
    """Normalize native Docker info and the Podman Docker-compatible info report."""
    host = document.get("host") or {}
    return {
        "os": document.get("OSType") or host.get("os"),
        "architecture": document.get("Architecture") or host.get("arch"),
        "cpus": document.get("NCPU") or host.get("cpus"),
        "memory": document.get("MemTotal") or host.get("memTotal"),
    }


def check_engine_resources(information):
    if information["os"] != "linux":
        raise HostError(
            "Select a local Linux container engine. On Windows use Docker Desktop's Linux containers."
        )
    if information["architecture"] not in {"amd64", "x86_64"}:
        raise HostError(
            "The pinned local ONLYOFFICE image requires an amd64 Linux container engine."
        )
    try:
        sufficient = (
            int(information["cpus"]) >= 4
            and int(information["memory"]) >= MIN_ENGINE_MEMORY
        )
    except (TypeError, ValueError):
        sufficient = False
    if not sufficient:
        raise HostError(
            "Allocate at least 4 CPUs and 8 GiB to the container engine: ONLYOFFICE needs 6 GiB plus backend capacity."
        )


def check_engine_transport(document):
    if "host" not in document:
        return
    remote = document["host"].get("serviceIsRemote")
    endpoint = os.environ.get("CONTAINER_HOST")
    if not isinstance(remote, bool) or (
        remote and (not endpoint or not bootstrap._is_local_engine_endpoint(endpoint))
    ):
        raise HostError(
            "The Podman service is remote or unverified. Select an explicit verified local container endpoint."
        )


def check_compose_version(version):
    match = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)", version)
    if not match or tuple(map(int, match.groups())) < (2, 24, 4):
        raise HostError(
            "A Compose provider supporting !override (Docker Compose 2.24.4 or newer) is required. Configure the local Podman Compose provider if applicable."
        )


def doctor():
    if sys.version_info[:2] < MIN_PYTHON:
        raise HostError(
            "Python 3.12 or newer is required. Install Python and reopen the terminal."
        )
    if platform.system() not in {"Linux", "Windows"}:
        raise HostError(
            "Unified local setup supports Linux and native Windows PowerShell."
        )
    environment = host_environment()
    for program in ("task", "git", "uv", "node", "npx", "bun", "docker"):
        executable(program)
    for program in ("task", "git", "uv", "npx", "bun"):
        result = run(
            [program, "--version"],
            env=environment,
            capture_output=True,
            check=False,
            timeout=15,
        )
        if result.returncode:
            raise HostError(
                f"{program} could not run. Check its installation and reopen the terminal."
            )
    version = run(
        ["node", "--version"], env=environment, capture_output=True, timeout=15
    ).stdout.strip()
    check_node_version(version)
    bootstrap._assert_local_engine()
    information = None
    for template in ("{{json .}}", "json"):
        result = run(
            ["docker", "info", "--format", template],
            env=environment,
            capture_output=True,
            check=False,
            timeout=30,
        )
        if result.returncode == 0:
            try:
                document = json.loads(result.stdout)
                check_engine_transport(document)
                information = engine_information(document)
                break
            except (ValueError, TypeError, AttributeError):
                continue
    if information is None:
        raise HostError(
            "The local container engine did not answer. Start Docker Desktop or the local Docker-compatible Podman service."
        )
    check_engine_resources(information)
    compose = run(
        ["docker", "compose", "version", "--short"],
        env=environment,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if compose.returncode:
        raise HostError(
            "The Compose provider is unavailable. Install Docker Compose or configure Podman's Docker-compatible provider."
        )
    check_compose_version(compose.stdout)
    run([sys.executable, "tools/scripts/sync.py", "doctor"], cwd=ROOT, env=environment)
    sys.stdout.write("[COMPLETED] Local setup prerequisites verified.\n")


def fresh_project():
    digest = hashlib.sha256(os.path.normcase(str(ROOT)).encode()).hexdigest()[:12]
    return f"medilab-bootstrap-{digest}"


def classify():
    project = project_name()
    marker = bootstrap._read_marker()
    if marker is not None:
        if not isinstance(marker, dict) or not marker:
            raise HostError(
                "The local bootstrap ownership marker is invalid. Inspect it before setup."
            )
        bootstrap._validate_setup_marker(project, marker)
        return (
            "completed-fresh" if marker.get("status") == "completed" else "fresh"
        ), marker
    bootstrap.check_normal_setup()
    if any(bootstrap._resources(project).values()):
        return "ordinary", None
    bootstrap.select(fresh_project())
    marker = bootstrap._read_marker()
    if not marker or marker.get("status") != "selected":
        raise HostError("The empty local environment could not be selected safely.")
    return "fresh", marker


def fresh_environment(marker, dotenv):
    if (
        not isinstance(marker, dict)
        or not marker.get("project")
        or not marker.get("owner")
        or not isinstance(marker.get("config"), dict)
    ):
        raise HostError(
            "The fresh environment ownership configuration is unavailable. Inspect setup recovery guidance."
        )
    environment = bootstrap._compose_environment(
        marker["project"], marker["owner"], marker["config"]
    )
    environment.update(host_environment())
    # Nested Task calls must not reload the caller's private dotenv files.
    environment["MEDILAB_SETUP_DOTENV"] = str(dotenv)
    return environment


def task(name, environment, *arguments):
    run(["task", name, *arguments], cwd=ROOT, env=environment)


def component(name, operation, environment):
    run(
        [sys.executable, f"tools/scripts/{name}.py", operation],
        cwd=ROOT,
        env=environment,
    )


def prepare(mode, marker, environment, modules):
    if mode == "ordinary":
        executable("doppler")
        bootstrap.check_normal_setup()
    elif mode == "completed-fresh":
        bootstrap.check_normal_setup()
    if mode != "fresh":
        component("onlyoffice", "recover-registration", environment)
        if marker:
            refreshed = bootstrap._read_marker()
            if not isinstance(refreshed, dict) or any(
                refreshed.get(key) != marker.get(key) for key in ("project", "owner")
            ):
                raise HostError(
                    "The selected ownership changed during addon recovery. Refusing further setup."
                )
            environment = fresh_environment(
                refreshed, environment["MEDILAB_SETUP_DOTENV"]
            )
    if mode == "ordinary":
        component("onlyoffice", "guard-existing", environment)
        task("doppler", environment)
    task("dev:setup", environment)
    task("ai:setup", environment)
    if mode == "fresh":
        run(
            [sys.executable, "tools/scripts/demo_bootstrap.py", "setup"],
            cwd=ROOT,
            env=environment,
        )
    else:
        task("upgrade", environment, f"MODULES={modules}")
    component("sync", "verify", environment)
    component("onlyoffice", "setup", environment)
    component("sync", "setup", environment)
    component("onlyoffice", "verify", environment)
    component("sync", "verify", environment)


def setup():
    modules = os.environ.get("MEDILAB_SETUP_MODULES", "all")
    if modules != "all" and not re.fullmatch(
        r"[a-zA-Z0-9_]+(?:[, ][a-zA-Z0-9_]+)*", modules
    ):
        raise HostError("MODULES must contain comma- or space-separated module names.")
    doctor()
    mode, marker = classify()
    if marker:
        with tempfile.TemporaryDirectory(prefix="medilab-setup-") as directory:
            dotenv = Path(directory) / "empty.env"
            dotenv.write_text("", encoding="utf-8")
            prepare(mode, marker, fresh_environment(marker, dotenv), modules)
    else:
        prepare(mode, marker, os.environ.copy(), modules)
    sys.stdout.write(
        "[COMPLETED] Odoo, ONLYOFFICE and Sync development setup verified. Use task sync:dev to open the native app.\n"
    )


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"setup", "doctor"}:
        sys.stderr.write("Usage: local_setup.py setup|doctor\n")
        return 2
    try:
        (setup if sys.argv[1] == "setup" else doctor)()
    except subprocess.CalledProcessError as error:
        return error.returncode or 1
    except (
        HostError,
        bootstrap.BootstrapError,
        ValueError,
        OSError,
        subprocess.TimeoutExpired,
    ) as error:
        sys.stderr.write(f"{error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
