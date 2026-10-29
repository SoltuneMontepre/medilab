"""Run only the ONLYOFFICE harness stack. Leaves failed-run volumes intact until explicit cleanup."""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

if __package__:
    from . import fixture_tls, native_results
    from .isolation import validate_network, validate_plan, validate_runtime
else:
    import fixture_tls
    import native_results
    from isolation import validate_network, validate_plan, validate_runtime

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = Path(__file__).with_name("compose.yml")
PROJECT = os.environ.get("ONLYOFFICE_COMPOSE_PROJECT", "medilab-onlyoffice")
if not re.fullmatch(r"medilab-onlyoffice(?:-[a-z0-9-]+)?", PROJECT):
    raise ValueError("Select an isolated ONLYOFFICE harness Compose project.")
RUNNER_SUFFIX = os.environ.get("ONLYOFFICE_RUNNER_SUFFIX", "")
if RUNNER_SUFFIX and not re.fullmatch(r"[a-z0-9-]+", RUNNER_SUFFIX):
    raise ValueError("ONLYOFFICE_RUNNER_SUFFIX must be a simple container suffix.")
CONTAINER = PROJECT + "-acceptance" + ("-" + RUNNER_SUFFIX if RUNNER_SUFFIX else "")
DATABASE = os.environ.get("ONLYOFFICE_TEST_DATABASE", "medilab_onlyoffice")
if not re.fullmatch(r"medilab_onlyoffice[a-z0-9_]{0,40}", DATABASE):
    raise ValueError("Select an isolated medilab_onlyoffice test database.")
EVIDENCE_DIRECTORY = "/var/lib/odoo/onlyoffice-integration/" + DATABASE
DIGEST = "sha256:3ab6ebc7c605e5a32b7ae3ff19daed4925090245acc8100ce2230bd766c88212"
IMAGE = "docker.io/onlyoffice/documentserver:9.4.0.1@" + DIGEST
RUN_ID = os.environ.get("ONLYOFFICE_RUN_ID", "current")
if not re.fullmatch(r"[a-zA-Z0-9_-]+", RUN_ID):
    raise ValueError("ONLYOFFICE_RUN_ID must be a simple local directory name.")
OUTPUT = ROOT / ".local/onlyoffice-harness" / RUN_ID
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
TLS_DIRECTORY = ROOT / ".local/onlyoffice-tls" / PROJECT
DOCKER_ENV["ONLYOFFICE_FIXTURE_TLS_DIRECTORY"] = str(TLS_DIRECTORY)
DOCKER_ENV["ONLYOFFICE_RUNNER_HOSTNAME"] = CONTAINER
DOCKER = ["docker", "--host=unix://" + SOCKET]


def command(args, **options):
    options.setdefault("timeout", 60)
    try:
        return subprocess.run(args, check=False, text=True, capture_output=True, **options)
    except OSError:
        return subprocess.CompletedProcess(args, 127, "", "Executable unavailable")


def compose(*args, **options):
    invocation = [*DOCKER, "compose", "-p", PROJECT, "-f", str(COMPOSE)]
    if extra := os.environ.get("ONLYOFFICE_COMPOSE_OVERRIDE"):
        override = Path(extra).resolve()
        if not override.is_relative_to(ROOT):
            raise ValueError("The test override must belong to this worktree.")
        invocation.extend(["-f", str(override)])
    return command([*invocation, *args], env=DOCKER_ENV, **options)


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
    account = os.environ.get("ONLYOFFICE_GITHUB_USER", "")
    if not account:
        return {"verified": False, "reason": "Set ONLYOFFICE_GITHUB_USER to the stored GitHub CLI account"}
    token = command(["gh", "auth", "token", "--hostname", "github.com", "--user", account], env=environment)
    if token.returncode or not token.stdout.strip():
        return {"verified": False, "reason": "Stored token of ONLYOFFICE_GITHUB_USER unavailable"}
    environment["GH_TOKEN"] = token.stdout.strip()
    user = command(["gh", "api", "user", "--jq", ".login"], env=environment)
    verified = user.returncode == 0 and user.stdout.strip() == account
    return {
        "verified": verified,
        "reason": "Exact account verified" if verified else "Exact account verification failed",
    }


def preflight():
    result = {
        "at": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "openssl_available": shutil.which("openssl") is not None,
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
    result["ready"] = all(
        (result["github"]["verified"], result["local_tcp"], result["docker_available"], result["openssl_available"])
    )
    write_result("preflight.json", result)
    return result["ready"]


def require_success(result, label):
    if result.returncode:
        raise RuntimeError(f"{label} failed with exit code {result.returncode}; inspect the isolated service locally.")
    return result


def verify_isolation():
    planned = require_success(compose("config", "--format", "json"), "Read fixture network plan")
    validate_plan(json.loads(planned.stdout), PROJECT)
    network = PROJECT + "_default"
    inspected = require_success(
        command([*DOCKER, "network", "inspect", network], env=DOCKER_ENV),
        "Inspect fixture network",
    )
    members = require_success(
        command(
            [
                *DOCKER,
                "ps",
                "-q",
                "--filter",
                "network=" + network,
                "--filter",
                "status=running",
            ],
            env=DOCKER_ENV,
        ),
        "Find fixture network peers",
    ).stdout.split()
    if not members:
        raise RuntimeError("No running fixture peers found.")
    containers = require_success(
        command([*DOCKER, "inspect", *members], env=DOCKER_ENV),
        "Inspect fixture network peers",
    )
    result = validate_runtime(PROJECT, json.loads(inspected.stdout)[0], json.loads(containers.stdout))
    write_result("isolation.json", result)
    return result


def verify_image():
    verify_isolation()
    containers = require_success(
        command(
            [
                *DOCKER,
                "ps",
                "-q",
                "--filter",
                "label=com.docker.compose.project=" + PROJECT,
                "--filter",
                "label=com.docker.compose.service=documentserver",
                "--filter",
                "status=running",
            ],
            env=DOCKER_ENV,
        ),
        "Find Document Server",
    ).stdout.split()
    if len(containers) != 1:
        raise RuntimeError("Expected exactly one running Document Server in this project.")
    container = containers[0]
    inspection = require_success(command([*DOCKER, "inspect", container], env=DOCKER_ENV), "Inspect container")
    running = json.loads(inspection.stdout)[0]
    image = require_success(command([*DOCKER, "image", "inspect", running["Image"]], env=DOCKER_ENV), "Inspect image")
    metadata = json.loads(image.stdout)[0]
    if not running["Config"]["Image"].endswith("@" + DIGEST) or not any(
        value.endswith("@" + DIGEST) for value in metadata["RepoDigests"]
    ):
        raise RuntimeError("The running container does not match the exact pinned digest.")
    version = require_success(
        command(
            [*DOCKER, "exec", container, "dpkg-query", "-W", "-f=${Version}", "onlyoffice-documentserver"],
            env=DOCKER_ENV,
        ),
        "Read package version",
    ).stdout.strip()
    if version != "9.4.0-129":
        raise RuntimeError("Unexpected Document Server package version: " + version)
    sources = require_success(
        command(
            [
                *DOCKER,
                "exec",
                container,
                "sha256sum",
                "/var/www/onlyoffice/documentserver/server/DocService/docservice",
                "/var/www/onlyoffice/documentserver/server/FileConverter/converter",
            ],
            env=DOCKER_ENV,
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
    fixture_tls.prepare(TLS_DIRECTORY, PROJECT)
    write_result(
        "tls.json",
        {"ca_sha256": fixture_tls.fingerprint(TLS_DIRECTORY), "disposable": True},
    )
    planned = require_success(compose("config", "--format", "json"), "Read fixture network plan")
    validate_plan(json.loads(planned.stdout), PROJECT)
    network = PROJECT + "_default"
    existing = command([*DOCKER, "network", "inspect", network], env=DOCKER_ENV)
    if existing.returncode:
        require_success(
            command(
                [
                    *DOCKER,
                    "network",
                    "create",
                    "--driver",
                    "bridge",
                    "--internal",
                    "--opt",
                    "isolate=strict",
                    "--label",
                    "com.docker.compose.project=" + PROJECT,
                    network,
                ],
                env=DOCKER_ENV,
            ),
            "Create strictly isolated fixture bridge",
        )
    else:
        from_network = json.loads(existing.stdout)[0]
        from_isolation = validate_network(PROJECT, from_network)
        if from_isolation != network:
            raise RuntimeError("Fixture network ownership mismatch.")
    if f"/run/user/{os.getuid()}/podman/podman.sock" == SOCKET:
        ca = os.environ.get("ONLYOFFICE_TEST_CA_BUNDLE", "/etc/ssl/certs/ca-certificates.crt")
        require_success(
            command(
                [
                    "podman",
                    "build",
                    "--secret",
                    "id=proxy_ca,src=" + ca,
                    "-f",
                    str(COMPOSE.with_name("browser.Dockerfile")),
                    "-t",
                    "localhost/medilab-onlyoffice-browser:local",
                    str(ROOT),
                ],
                timeout=600,
            ),
            "Build test browser",
        )
    else:
        require_success(compose("build", "browser", timeout=600), "Build test browser")
    require_success(
        compose(
            "up",
            "-d",
            "--wait",
            "--wait-timeout",
            "660",
            "postgres",
            "garage",
            "garage-tls",
            "documentserver",
            "browser",
            timeout=690,
        ),
        "Start isolated services",
    )
    verify_isolation()
    require_success(compose("run", "--rm", "garage-setup"), "Initialize isolated bucket")
    verify_image()


def check_test_run(native_only):
    if native_only and (
        not os.environ.get("ONLYOFFICE_REAL_TAGS") or "onlyoffice_real" in os.environ["ONLYOFFICE_REAL_TAGS"]
    ):
        raise ValueError("Select explicit native Odoo test tags without onlyoffice_real for test-native.")
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
            "harness",
            "-d",
            "postgres",
            "-Atc",
            f"SELECT datname FROM pg_database WHERE datname = '{DATABASE}'",
        ),
        "Check database ownership",
    )
    if database.stdout.strip():
        raise RuntimeError("The test database already exists; preserve evidence before explicit cleanup.")
    fixture_tls.prepare_runner(TLS_DIRECTORY, PROJECT, CONTAINER)


def wait_for_runner(launch, limit):
    deadline = time.monotonic() + limit
    observations = native_results.NativeResults()
    while True:
        inspected = require_success(command([*DOCKER, "inspect", CONTAINER], env=DOCKER_ENV), "Inspect test runner")
        state = json.loads(inspected.stdout)[0]["State"]
        observations.observe(command([*DOCKER, "logs", CONTAINER], env=DOCKER_ENV))
        if not state["Running"]:
            code = state["ExitCode"]
            break
        if time.monotonic() >= deadline:
            require_success(
                command([*DOCKER, "stop", "--time", "10", CONTAINER], env=DOCKER_ENV), "Stop timed-out test runner"
            )
            code = 124
            break
        time.sleep(2)
    logs_result = command([*DOCKER, "logs", CONTAINER], env=DOCKER_ENV)
    observations.observe(logs_result)
    result = subprocess.CompletedProcess(launch.args, code, logs_result.stdout, logs_result.stderr)
    return result, observations


def test(*, native_only=False):
    check_test_run(native_only)
    limit = int(os.environ.get("ONLYOFFICE_RUN_TIMEOUT", "1200"))
    launch = require_success(
        compose(
            "run",
            "--detach",
            "--name",
            CONTAINER,
            *(
                ["--use-aliases"]
                if not native_only or "onlyoffice_page_real" in os.environ.get("ONLYOFFICE_REAL_TAGS", "")
                else []
            ),
            "--no-deps",
            "runner",
        ),
        "Launch test runner",
    )
    result, observations = wait_for_runner(launch, limit)
    copy = command(
        [*DOCKER, "cp", CONTAINER + ":" + EVIDENCE_DIRECTORY + "/.", str(OUTPUT / "callbacks")], env=DOCKER_ENV
    )
    files = sorted((OUTPUT / "callbacks").glob("test_*.json")) if copy.returncode == 0 else []
    source = ROOT / "src/core/modules/sol_laboratory/tests/test_onlyoffice_real.py"
    expected_names = native_results.expected_test_names(source, native_only, os.environ.get("ONLYOFFICE_TEST_METHOD"))
    outcomes = native_results.callback_outcomes(result, files, expected_names, observations.successful_summary())
    passed = bool(
        result.returncode == 0
        and len(files) == len(expected_names)
        and not outcomes["failed_tests"]
        and not observations.failed
        and observations.started
        and observations.successful_summary()
    )
    write_result(
        "result.json",
        {
            "at": datetime.now(UTC).isoformat(),
            "runner_exit": result.returncode,
            "database": DATABASE,
            "container": CONTAINER,
            "evidence_copy_exit": copy.returncode,
            "evidence_files": [path.name for path in files],
            "runner_log_sha256": hashlib.sha256((result.stdout + result.stderr).encode()).hexdigest(),
            "real_service_executed": not native_only,
            "native_odoo_executed": True,
            "native_test_status": observations.statuses(result.returncode),
            "native_summary": observations.summaries,
            "passed": passed,
            **outcomes,
            "whole_runner_timeout_seconds": limit,
        },
    )
    if not passed:
        raise RuntimeError("Real-service acceptance failed or lacks complete evidence; no acceptance claimed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "start", "test", "test-native", "down"))
    args = parser.parse_args()
    if args.action == "down":
        require_success(compose("down", "--volumes", "--remove-orphans"), "Remove the harness stack")
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
    elif args.action == "test-native":
        test(native_only=True)


if __name__ == "__main__":
    main()
