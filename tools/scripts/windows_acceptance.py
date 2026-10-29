"""Collect native Windows 11 setup evidence; default Doctor never initializes a project.

Use windows_acceptance.ps1 from native PowerShell 5.1/7. -RunSetup requires an empty linked worktree.
"""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import demo_bootstrap as bootstrap
import local_acceptance_snapshot as snapshots
import local_setup
from host_tools import HostError, process_arguments
from windows_acceptance_host import host_identity, prerequisite_inventory

ROOT = Path(__file__).resolve().parents[2]
PRIVATE_CONFIG = (
    ".env",
    ".env.local",
    ".doppler.yaml",
    "doppler.yaml",
    "src/core/.env.local",
    "tools/infrastructure/.env",
    ".local/demo-bootstrap.json",
    ".local/demo-bootstrap-switch.json",
    ".local/demo-bootstrap-selections",
    ".local/onlyoffice",
    ".local/sync-development.json",
)
BASH_PATH = re.compile(
    r"(?i)[\\/]Git[\\/](?:usr[\\/]bin|bin)(?:[\\/]|$)|[\\/]msys64[\\/]"
)
STAGES = (
    ("fresh_setup", ("task", "setup")),
    ("repeated_setup", ("task", "setup")),
    ("onlyoffice_verify", ("task", "onlyoffice:verify")),
    ("sync_test", ("task", "sync:test")),
    ("sync_lint", ("task", "sync:lint")),
    ("sync_check", ("task", "sync:check")),
    ("sync_build", ("task", "sync:build")),
)


class AcceptanceError(RuntimeError):
    pass


def git(root, *arguments):
    return subprocess.check_output(
        ["git", *arguments],
        cwd=root,
        text=True,
        encoding="utf-8",
        stderr=subprocess.PIPE,
    ).strip()


def source_identity(root):
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).split(b"\0")
    rows = []
    for name in sorted(names):
        if name:
            path = root / os.fsdecode(name)
            if path.is_file():
                rows.append(
                    (os.fsdecode(name), hashlib.sha256(path.read_bytes()).hexdigest())
                )
    return {
        "head": git(root, "rev-parse", "HEAD"),
        "tracked_sha256": hashlib.sha256(json.dumps(rows).encode()).hexdigest(),
    }


def require_empty_worktree(root):
    if not (root / ".git").is_file() or git(root, "status", "--porcelain"):
        raise AcceptanceError(
            "RunSetup requires a clean, separate linked Git worktree."
        )
    git_directory = Path(git(root, "rev-parse", "--absolute-git-dir")).resolve()
    common_directory = Path(
        git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    ).resolve()
    if git_directory == common_directory:
        raise AcceptanceError(
            "RunSetup requires a clean, separate linked Git worktree."
        )
    path = str(root)
    if not any(character.isspace() for character in path) or not any(
        ord(character) > 127 for character in path
    ):
        raise AcceptanceError(
            "The linked worktree path must contain both a space and a non-ASCII character."
        )
    from local_private_paths import guard_local_path

    guard_local_path(root, root / ".local" / "windows-acceptance")
    if any(
        (root / relative).is_symlink()
        or (
            (root / relative).exists()
            and (
                relative.startswith(".local/")
                or not git(root, "ls-files", "--", relative)
            )
        )
        for relative in PRIVATE_CONFIG
    ):
        raise AcceptanceError(
            "Existing local configuration or application ownership must be preserved in another worktree."
        )
    bootstrap._assert_local_engine()
    from compose_env import project_name

    ordinary, fresh = project_name(), local_setup.fresh_project()
    for project in {ordinary, fresh}:
        bootstrap._assert_no_resources(project)
    return fresh


class Evidence:
    def __init__(self, root):
        from local_private_paths import (
            ensure_local_directory,
            guard_local_path,
            protect_created_path,
        )

        self.root = root
        self.relative = Path(".local/windows-acceptance") / uuid.uuid4().hex
        ensure_local_directory(root, root / self.relative.parent)
        self.directory = guard_local_path(root, root / self.relative)
        self.directory.mkdir(mode=0o700)
        protect_created_path(root, self.directory)

    def create(self, name, data=b""):
        from local_private_paths import protect_created_path

        path = self.directory / name
        private_output(self.root, self.directory)
        private_output(self.root, path)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        protect_created_path(self.root, path)
        return path

    def write(self, report):
        write_evidence(self.root, self.directory / "evidence.json", report)


def private_output(root, path):
    from local_private_paths import guard_local_path, windows_private_acl

    path = guard_local_path(root, path)
    if path.exists():
        if os.name == "nt":
            windows_private_acl(path)
        elif stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise AcceptanceError(
                "Acceptance evidence must remain private to the current user."
            )
    return path


def write_evidence(root, destination, report):
    from local_private_paths import protect_created_path

    private_output(root, destination.parent)
    private_output(root, destination)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".evidence-", dir=destination.parent
    )
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        protect_created_path(root, temporary)
        private_output(root, destination)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def setup_environment(evidence):
    environment = local_setup.host_environment()
    guard = evidence.directory / "native-command-guard"
    from local_private_paths import ensure_local_directory

    ensure_local_directory(evidence.root, guard)
    for name in ("bash.cmd", "sh.cmd"):
        evidence.create("native-command-guard/" + name, b"@exit /b 97\r\n")
    empty = evidence.create("empty.env")
    entries = [
        entry
        for entry in environment["PATH"].split(os.pathsep)
        if not BASH_PATH.search(entry)
    ]
    environment.update(
        PATH=str(guard) + os.pathsep + os.pathsep.join(entries),
        MEDILAB_SETUP_DOTENV=str(empty),
        PYTHONUTF8="1",
        PYTHONDONTWRITEBYTECODE="1",
        RUSTUP_AUTO_INSTALL="0",
        NO_COLOR="1",
    )
    return environment


def verify_frozen(root, source):
    if git(root, "status", "--porcelain") or source_identity(root) != source:
        raise AcceptanceError(
            "The worktree revision or tracked source changed during acceptance."
        )


def selected_owner(project):
    marker = bootstrap._read_marker()
    if (
        not marker
        or marker.get("project") != project
        or marker.get("status") != "completed"
    ):
        raise AcceptanceError(
            "The setup did not produce the expected completed fresh selection."
        )
    owner = marker.get("owner")
    if not isinstance(owner, str) or str(uuid.UUID(owner)) != owner:
        raise AcceptanceError("The selected fresh ownership UUID is invalid.")
    snapshots.selected(project, owner)
    return owner


def run_stage(command, *, root, environment, stream):
    process = subprocess.Popen(
        process_arguments(command, environment),
        cwd=root,
        env=environment,
        stdout=stream,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    try:
        return process.wait(timeout=5400)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        if process.poll() is None:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                    env=environment,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    timeout=30,
                    check=False,
                )
            else:
                process.kill()
            process.wait(timeout=30)
        raise AcceptanceError(
            "An acceptance command was interrupted or timed out; command cleanup was attempted and project resources retained."
        ) from None


def snapshot_differences(baseline, current):
    if baseline is None:
        return None
    return {
        section: {"baseline": baseline.get(section), "actual": current.get(section)}
        for section in sorted(set(baseline) | set(current))
        if baseline.get(section) != current.get(section)
    }


def failure_snapshot(report, evidence, project, owner, baseline):
    result = {"stage": report["stage"]}
    try:
        current = snapshots.capture(project, owner or selected_owner(project))
        result.update(
            snapshot=current, integrity_diff=snapshot_differences(baseline, current)
        )
        if baseline is not None:
            report["failure_integrity_unchanged"] = current == baseline
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        result["error_type"] = type(error).__name__
    report["failure_snapshot"] = result
    try:
        evidence.write(report)
    except (OSError, RuntimeError):
        report["failure_snapshot_evidence_write_failed"] = True


def execute_setup(root, report):
    project = require_empty_worktree(root)
    source = source_identity(root)
    evidence = Evidence(root)
    report.update(
        source=source,
        project=project,
        evidence=(evidence.relative / "evidence.json").as_posix(),
        worktree_path={
            "has_space": any(character.isspace() for character in str(root)),
            "has_non_ascii": any(ord(character) > 127 for character in str(root)),
            "sha256": hashlib.sha256(str(root).encode()).hexdigest(),
        },
    )
    environment = setup_environment(evidence)
    baseline = None
    owner = None
    evidence.write(report)
    for name, command in STAGES:
        verify_frozen(root, source)
        if owner is not None:
            snapshots.selected(project, owner)
        log = evidence.create(name + ".log")
        started = time.monotonic()
        report["stage"] = name
        evidence.write(report)
        try:
            with log.open("ab") as stream:
                code = run_stage(
                    command, root=root, environment=environment, stream=stream
                )
        except (OSError, AcceptanceError, subprocess.SubprocessError) as error:
            report["stages"].append({"name": name, "error_type": type(error).__name__})
            failure_snapshot(report, evidence, project, owner, baseline)
            raise
        report["stages"].append(
            {
                "name": name,
                "exit": code,
                "seconds": round(time.monotonic() - started, 2),
            }
        )
        if code:
            failure_snapshot(report, evidence, project, owner, baseline)
            raise AcceptanceError(
                "An acceptance command failed; its private local log is retained."
            )
        evidence.write(report)
        verify_frozen(root, source)
        if owner is None:
            owner = selected_owner(project)
            baseline = snapshots.ready_baseline(project, owner)
            report.update(owner=owner, baseline=baseline)
            current = baseline
        else:
            current = snapshots.capture(project, owner)
        report.setdefault("stage_snapshots", {})[name] = current
        difference = snapshot_differences(baseline, current)
        report.setdefault("integrity_diffs", {})[name] = difference
        evidence.write(report)
        if difference:
            raise AcceptanceError(
                "Owned data, private fingerprints or volume identities changed."
            )
        if name != "fresh_setup":
            report["integrity_verified_after"] = name
        evidence.write(report)
    packages = sorted(
        (
            root / "src/applications/medilab-sync/src-tauri/target/release/bundle/nsis"
        ).glob("*.exe")
    )
    if not packages:
        raise AcceptanceError(
            "The native Windows build did not create an NSIS package."
        )
    report["packages"] = [
        {
            "name": package.name,
            "bytes": package.stat().st_size,
            "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
        }
        for package in packages
    ]
    report.update(
        status="passed",
        acceptance="passed",
        stage="completed",
        scope="Windows 11 native CLI setup, repeatability, conversion and Sync checks/build.",
        gui_acceptance="unverified",
        external_bash_disabled=True,
    )
    evidence.write(report)
    return evidence


def collect(*, run_setup=False, shell_version="", root=ROOT):
    report = {
        "schema_version": 1,
        "mode": "run_setup" if run_setup else "doctor",
        "status": "blocked",
        "acceptance": "unverified",
        "stage": "host",
        "stages": [],
    }
    try:
        if sys.version_info < (3, 12):
            raise AcceptanceError("Native Python 3.12 or newer is required.")
        report["host"] = host_identity(shell_version)
        if not report["host"]["windows11"]:
            report["reason"] = (
                "A directly running Windows 11 workstation is required; Server and other hosts are unverified."
            )
            return report, 2
        report["stage"] = "prerequisites"
        report["inventory"] = prerequisite_inventory(root)
        if run_setup:
            report["stage"] = "empty_worktree"
            execute_setup(root, report)
        else:
            report.update(status="doctor_passed", stage="completed")
        return report, 0
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
        KeyboardInterrupt,
    ) as error:
        report.update(
            status="failed", acceptance="unverified", error_type=type(error).__name__
        )
        if isinstance(error, (AcceptanceError, HostError, snapshots.SnapshotError)):
            report["reason"] = str(error)
        if report.get("evidence"):
            try:
                write_evidence(root, root / report["evidence"], report)
            except (OSError, RuntimeError):
                report["evidence_write_failed"] = True
        return report, 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-setup", action="store_true")
    parser.add_argument("--shell-version", default="")
    arguments = parser.parse_args()
    report, code = collect(
        run_setup=arguments.run_setup, shell_version=arguments.shell_version
    )
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
