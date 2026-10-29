"""Run native Sync tasks from the worktree root; preserve installed profiles and credential stores.

Usage: python tools/scripts/sync.py doctor|setup|dev|build|test|lint|check|verify|clean
"""

import argparse
import errno
import json
import os
import pathlib
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile

from host_tools import HostError, executable, run, selected_odoo_url
from sync_doctor import doctor
from sync_verify import validate_url, verify

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "src/applications/medilab-sync"
MANIFEST = "src-tauri/Cargo.toml"
METADATA = ROOT / ".local/sync-development.json"
OPERATIONS = (
    "doctor",
    "setup",
    "dev",
    "build",
    "test",
    "lint",
    "check",
    "verify",
    "clean",
)


def _plain_path(path, boundary):
    try:
        relative = path.relative_to(boundary)
    except ValueError as error:
        raise HostError("Sync output must stay inside this worktree.") from error
    current = boundary
    for part in relative.parts:
        current /= part
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            raise HostError(
                "Sync refuses output paths containing symlinks or junctions."
            )
    if not path.resolve().is_relative_to(boundary.resolve()):
        raise HostError("Sync output escapes this worktree.")


def save_endpoint(base):
    _plain_path(METADATA, ROOT)
    if METADATA.exists():
        try:
            saved = json.loads(METADATA.read_text(encoding="utf-8"))
        except (ValueError, OSError) as error:
            raise HostError(
                "The Sync development metadata is invalid; inspect it before running setup again."
            ) from error
        if (
            not isinstance(saved, dict)
            or saved.get("version") != 1
            or saved.get("worktree") != str(ROOT)
        ):
            raise HostError(
                "The Sync development metadata belongs to another worktree or unsupported version."
            )
    METADATA.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix="sync-development-", suffix=".json", dir=METADATA.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                {"version": 1, "worktree": str(ROOT), "odoo_url": base},
                stream,
                indent=2,
            )
            stream.write("\n")
        os.replace(temporary, METADATA)
    finally:
        pathlib.Path(temporary).unlink(missing_ok=True)


def _check_build_tree(target):
    for directory, folders, files in os.walk(target, followlinks=False):
        for name in (*folders, *files):
            _plain_path(pathlib.Path(directory) / name, ROOT)


def clean():
    targets = (APP / "dist", APP / "src-tauri/target")
    for target in targets:
        _plain_path(target, ROOT)
        if target.exists() and not target.is_dir():
            raise HostError("A fixed Sync build-output path is not a directory.")
        if target.exists():
            _check_build_tree(target)
    for target in targets:
        if target.exists():
            shutil.rmtree(target)


def _bun(arguments, env, *, capture=False):
    return run(
        [executable("bun"), *arguments], cwd=APP, env=env, capture_output=capture
    )


def _locked_cli(env):
    if not (APP / "node_modules").is_dir():
        raise HostError("Sync dependencies are missing. Run task sync:setup first.")
    lock = (APP / "bun.lock").read_text(encoding="utf-8")
    pinned = re.search(r'"@tauri-apps/cli":\s*\[\s*"@tauri-apps/cli@([^\"]+)"', lock)
    if not pinned:
        raise HostError("The Sync Bun lockfile does not identify its Tauri CLI.")
    output = _bun(["run", "tauri", "--version"], env, capture=True)
    installed = re.search(r"\btauri(?:-cli)?\s+([^\s]+)", output.stdout)
    if not installed or installed[1] != pinned[1]:
        raise HostError(
            "The installed Tauri CLI differs from bun.lock. Run task sync:setup with the frozen lockfile."
        )


def _free_dev_ports():
    for port in (1420, 1421):
        for family, address in (
            (socket.AF_INET, "127.0.0.1"),
            (socket.AF_INET6, "::1"),
        ):
            try:
                with socket.socket(family, socket.SOCK_STREAM) as probe:
                    probe.bind((address, port))
            except OSError as error:
                if family == socket.AF_INET6 and error.errno in {
                    errno.EAFNOSUPPORT,
                    errno.EADDRNOTAVAIL,
                    errno.EPROTONOSUPPORT,
                }:
                    continue
                raise HostError(
                    f"Sync dev port {port} is unavailable on loopback. Stop its owning process before launching another development instance."
                ) from error


def _check_build(operation, environment, base):
    if operation == "test":
        _bun(["test"], environment)
        run(
            [executable("cargo"), "test", "--locked", "--manifest-path", MANIFEST],
            cwd=APP,
            env=environment,
        )
    elif operation == "lint":
        run(
            [executable("cargo"), "fmt", "--check", "--manifest-path", MANIFEST],
            cwd=APP,
            env=environment,
        )
        run(
            [
                executable("cargo"),
                "clippy",
                "--locked",
                "--manifest-path",
                MANIFEST,
                "--all-targets",
                "--all-features",
                "--",
                "-D",
                "warnings",
            ],
            cwd=APP,
            env=environment,
        )
    elif operation in {"check", "setup"}:
        run(
            [executable("cargo"), "check", "--locked", "--manifest-path", MANIFEST],
            cwd=APP,
            env=environment,
        )
        if operation == "setup":
            verify(base)
            save_endpoint(base)


def _execute_build(operation, environment, base):
    if operation == "dev":
        _free_dev_ports()
        _bun(["run", "tauri:dev"], environment)
    elif operation == "build":
        bundles = "nsis" if platform.system() == "Windows" else "deb,rpm"
        _bun(
            ["run", "tauri", "build", "--bundles", bundles, "--", "--locked"],
            environment,
        )
    else:
        _bun(["run", "build"], environment)
        _check_build(operation, environment, base)


def execute(operation):
    if operation == "clean":
        clean()
        return
    if operation == "verify":
        doctor()
        verify(selected_odoo_url(require_saved_selection=True))
        return
    versions = doctor(gui=operation == "dev")
    if operation == "doctor":
        for name, version in versions.items():
            sys.stdout.write(f"{name}: {version}\n")
        return
    base = validate_url(
        selected_odoo_url(require_saved_selection=operation in {"setup", "dev"})
    )
    environment = {**os.environ, "MEDILAB_SYNC_ODOO_URL": base}
    if operation == "setup":
        _bun(["install", "--frozen-lockfile", "--ignore-scripts"], environment)
    _locked_cli(environment)
    if operation == "setup":
        run(
            [executable("cargo"), "fetch", "--locked", "--manifest-path", MANIFEST],
            cwd=APP,
            env=environment,
        )
    _execute_build(operation, environment, base)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=OPERATIONS)
    operation = parser.parse_args().operation
    try:
        execute(operation)
    except HostError as error:
        sys.stderr.write(f"Sync: {error}\n")
        return 1
    except subprocess.CalledProcessError as error:
        sys.stderr.write(
            f"Sync {operation} failed; the required tool exited with status {error.returncode}.\n"
        )
        return error.returncode if error.returncode > 0 else 1
    except (OSError, subprocess.TimeoutExpired):
        sys.stderr.write(
            "Sync could not complete the host operation. Check filesystem access and native tool readiness.\n"
        )
        return 1
    sys.stdout.write(f"Sync {operation} completed.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
