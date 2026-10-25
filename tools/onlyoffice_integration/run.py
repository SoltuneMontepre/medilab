"""Run only the Agent 4 stack. Leaves failed-run volumes intact until explicit cleanup."""

import argparse
import ast
import hashlib
import json
import os
import platform
import re
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = Path(__file__).with_name("compose.yml")
PROJECT = "medilab171-agent4"
CONTAINER = PROJECT + "-acceptance"
DIGEST = "sha256:3ab6ebc7c605e5a32b7ae3ff19daed4925090245acc8100ce2230bd766c88212"
IMAGE = "docker.io/onlyoffice/documentserver:9.4.0.1@" + DIGEST
RUN_ID = os.environ.get("ONLYOFFICE_RUN_ID", "current")
if not re.fullmatch(r"[a-zA-Z0-9_-]+", RUN_ID):
    raise ValueError("ONLYOFFICE_RUN_ID must be a simple local directory name.")
OUTPUT = ROOT / ".local/onlyoffice-agent4" / RUN_ID
DOCKER_ENV = {
    key: value
    for key, value in os.environ.items()
    if key
    not in (
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
    )
}
SOCKET = os.environ.get("ONLYOFFICE_CONTAINER_SOCKET", "/var/run/docker.sock")
if not SOCKET.startswith("/"):
    raise ValueError("ONLYOFFICE_CONTAINER_SOCKET must be an absolute local Unix socket path.")
DOCKER_ENV["DOCKER_HOST"] = "unix://" + SOCKET
DOCKER = ["docker", "--host=unix://" + SOCKET]


def command(args, **options):
    try:
        return subprocess.run(args, check=False, text=True, capture_output=True, **options)
    except OSError:
        return subprocess.CompletedProcess(args, 127, "", "Executable unavailable")


def compose(*args, **options):
    return command([*DOCKER, "compose", "-p", PROJECT, "-f", str(COMPOSE), *args], env=DOCKER_ENV, **options)


def write_result(name, result):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / name
    path.write_text(json.dumps(result, indent=2) + "\n")
    sys.stdout.write(str(path) + "\n")


def identity():
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in (
            "GH_TOKEN",
            "GITHUB_TOKEN",
            "GH_ENTERPRISE_TOKEN",
            "GITHUB_ENTERPRISE_TOKEN",
        )
    }
    token = command(["gh", "auth", "token", "--hostname", "github.com", "--user", "KietPham-VN"], env=environment)
    if token.returncode or not token.stdout.strip():
        return {"verified": False, "reason": "Stored KietPham-VN token unavailable"}
    environment["GH_TOKEN"] = token.stdout.strip()
    user = command(["gh", "api", "user", "--jq", ".login"], env=environment)
    verified = user.returncode == 0 and user.stdout.strip() == "KietPham-VN"
    return {
        "verified": verified,
        "reason": "Exact account verified" if verified else "Exact account verification failed",
    }


def preflight():
    result = {
        "at": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "expected_image": IMAGE,
        "github": identity(),
        "real_service_executed": False,
    }
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
        result["local_tcp"] = True
    except OSError as error:
        result["local_tcp"] = False
        result["socket_error"] = {"type": type(error).__name__, "errno": error.errno}
    runtime = command([*DOCKER, "version", "--format", "json"], env=DOCKER_ENV)
    result["docker_available"] = runtime.returncode == 0
    # Runtime errors may contain credential-bearing URLs; record only the exit status.
    result["docker_exit"] = runtime.returncode
    if runtime.returncode == 0:
        result["docker_version"] = json.loads(runtime.stdout)
    result["container_socket"] = SOCKET
    result["ready"] = all((result["github"]["verified"], result["local_tcp"], result["docker_available"]))
    write_result("preflight.json", result)
    return result["ready"]


def require_success(result, label):
    if result.returncode:
        raise RuntimeError(f"{label} failed with exit code {result.returncode}; inspect the isolated service locally.")
    return result


def verify_image():
    container = require_success(compose("ps", "-q", "documentserver"), "Find Document Server").stdout.strip()
    inspection = require_success(command([*DOCKER, "inspect", container], env=DOCKER_ENV), "Inspect container")
    running = json.loads(inspection.stdout)[0]
    image = require_success(command([*DOCKER, "image", "inspect", running["Image"]], env=DOCKER_ENV), "Inspect image")
    metadata = json.loads(image.stdout)[0]
    if not running["Config"]["Image"].endswith("@" + DIGEST) or not any(
        value.endswith("@" + DIGEST) for value in metadata["RepoDigests"]
    ):
        raise RuntimeError("The running container does not match the exact pinned digest.")
    version = require_success(
        compose("exec", "-T", "documentserver", "dpkg-query", "-W", "-f=${Version}", "onlyoffice-documentserver"),
        "Read package version",
    ).stdout.strip()
    if version != "9.4.0-129":
        raise RuntimeError("Unexpected Document Server package version: " + version)
    sources = require_success(
        compose(
            "exec",
            "-T",
            "documentserver",
            "sha256sum",
            "/var/www/onlyoffice/documentserver/server/DocService/docservice",
            "/var/www/onlyoffice/documentserver/server/FileConverter/converter",
        ),
        "Hash upstream source",
    )
    write_result(
        "runtime.json",
        {
            "at": datetime.now(UTC).isoformat(),
            "configured_image": IMAGE,
            "image_id": metadata["Id"],
            "repo_digests": metadata["RepoDigests"],
            "architecture": metadata["Architecture"],
            "os": metadata["Os"],
            "container_started": running["State"]["StartedAt"],
            "package_version": version,
            "upstream_binary_sha256": sources.stdout.splitlines(),
            "reviewed_base": "fa8031db9eee3108211d771e09a57f20c038e4ad",
            "harness_commit": command(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip(),
            "callback_commit": command(
                [
                    "git",
                    "log",
                    "-1",
                    "--format=%H",
                    "--",
                    "src/core/modules/sol_laboratory/services/editing_callback_logging.py",
                ],
                cwd=ROOT,
            ).stdout.strip(),
            "uncommitted_diff_sha256": hashlib.sha256(
                command(["git", "diff", "HEAD"], cwd=ROOT).stdout.encode()
            ).hexdigest(),
        },
    )


def start():
    browser = command([*DOCKER, "image", "inspect", "localhost/medilab171-agent4-browser:local"], env=DOCKER_ENV)
    if browser.returncode:
        require_success(compose("build", "browser"), "Build test browser")
    require_success(
        compose("up", "-d", "--wait", "--wait-timeout", "660", "postgres", "garage", "documentserver", "browser"),
        "Start isolated services",
    )
    require_success(compose("run", "--rm", "garage-setup"), "Initialize isolated bucket")
    verify_image()


def test():
    verify_image()
    if (OUTPUT / "callbacks").exists():
        raise RuntimeError("This run already has callback evidence; select a new ONLYOFFICE_RUN_ID.")
    exists = command([*DOCKER, "inspect", CONTAINER], env=DOCKER_ENV)
    if exists.returncode == 0:
        raise RuntimeError("Acceptance container already exists; preserve evidence, then explicitly clean this stack.")
    database = require_success(
        compose(
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "agent4",
            "-d",
            "postgres",
            "-Atc",
            "SELECT datname FROM pg_database WHERE datname = 'medilab171agent4'",
        ),
        "Check database ownership",
    )
    if database.stdout.strip():
        raise RuntimeError("The test database already exists; preserve evidence before explicit cleanup.")
    result = compose("run", "--name", CONTAINER, "--use-aliases", "--no-deps", "runner")
    copy = command([*DOCKER, "cp", CONTAINER + ":/tmp/agent4-evidence/.", str(OUTPUT / "callbacks")], env=DOCKER_ENV)
    files = sorted((OUTPUT / "callbacks").glob("test_*.json")) if copy.returncode == 0 else []
    # Do not persist raw Odoo/Document Server logs: inspect them locally under restricted access.
    source = ROOT / "src/core/modules/sol_laboratory/tests/test_onlyoffice_real.py"
    expected_names = sorted(
        node.name
        for node in ast.walk(ast.parse(source.read_text()))
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    )
    expected = len(expected_names)
    logs = result.stdout + result.stderr
    failed = sorted(set(re.findall(r"(?:FAIL|ERROR): TestOnlyofficeReal\.(test_\w+)", logs)))
    started = sorted(set(re.findall(r"Starting TestOnlyofficeReal\.(test_\w+)", logs)))
    passed = (
        result.returncode == 0 and len(files) == expected and "0 failed, 0 error(s)" in result.stdout + result.stderr
    )
    write_result(
        "result.json",
        {
            "at": datetime.now(UTC).isoformat(),
            "runner_exit": result.returncode,
            "evidence_copy_exit": copy.returncode,
            "evidence_files": [path.name for path in files],
            "runner_log_sha256": hashlib.sha256((result.stdout + result.stderr).encode()).hexdigest(),
            "real_service_executed": True,
            "passed": passed,
            "failed_tests": failed,
            "passed_tests": [name for name in started if name not in failed],
            "not_started_tests": [name for name in expected_names if name not in started],
        },
    )
    if not passed:
        raise RuntimeError("Real-service acceptance failed or lacks complete evidence; no acceptance claimed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "start", "test", "down"))
    args = parser.parse_args()
    if args.action == "down":
        require_success(compose("down", "--volumes", "--remove-orphans"), "Remove Agent 4 stack")
        leftover = command([*DOCKER, "inspect", CONTAINER], env=DOCKER_ENV)
        if leftover.returncode == 0:
            metadata = json.loads(leftover.stdout)[0]
            if metadata["Config"]["Labels"].get("com.docker.compose.project") != PROJECT:
                raise RuntimeError("Refusing removal of a container owned by another project.")
            require_success(command([*DOCKER, "rm", CONTAINER], env=DOCKER_ENV), "Remove stopped test runner")
        return
    if not preflight():
        sys.exit("Preflight failed; real-service tests were not executed.")
    if args.action == "start":
        start()
    elif args.action == "test":
        test()


if __name__ == "__main__":
    main()
