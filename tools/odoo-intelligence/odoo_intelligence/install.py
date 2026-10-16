"""Install checksummed official releases without replacing running tools."""

import hashlib
import json
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from filelock import FileLock

from .workspace import RELEASE, Workspace


def unpack_verified(archive: Path, destination: Path, digest: str) -> None:
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise ValueError(f"SHA-256 mismatch for {archive.name}; installation was not changed.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as staging:
        stage = Path(staging) / "contents"
        stage.mkdir()
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as source:
                for member in source.infolist():
                    if not (stage / member.filename).resolve().is_relative_to(stage) or member.filename.startswith("/"):
                        raise ValueError("Unsafe path in release archive.")
                    if member.external_attr >> 16 & 0o170000 == 0o120000:
                        raise ValueError("Unexpected symlink in release archive.")
                source.extractall(stage)
        else:
            with tarfile.open(archive) as source:
                source.extractall(stage, filter="data")
        stage.rename(destination)


def platform_asset() -> str:
    system = {"Linux": "linux", "Darwin": "darwin", "Windows": "win32"}.get(platform.system())
    architecture = {"x86_64": "x86_64", "AMD64": "x86_64", "arm64": "aarch64", "aarch64": "aarch64"}.get(
        platform.machine()
    )
    if system is None or architecture is None:
        raise ValueError(f"Unsupported OdooLS platform: {platform.system()} {platform.machine()}")
    if system == "linux" and platform.libc_ver()[0] != "glibc":
        system = "alpine"
    extension = "zip" if system == "win32" else "tar.gz"
    return f"odoo-{system}-{architecture}-{RELEASE['version']}.{extension}"


def install_release(workspace: Workspace) -> None:
    if workspace.binary.is_file():
        actual = subprocess.check_output([str(workspace.binary), "--version"], text=True).strip()
        if (
            actual != f"odoo_ls_server {RELEASE['version']}"
            or not (workspace.release / "typeshed/stdlib/builtins.pyi").is_file()
        ):
            raise RuntimeError("Incomplete OdooLS release; move this worktree's release directory aside and reinstall.")
        return
    workspace.release.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=workspace.local) as staging:
        stage = Path(staging)
        unpacked = stage / "release"
        for asset, destination in [(platform_asset(), unpacked), ("typeshed.zip", unpacked / "typeshed")]:
            download = stage / asset
            url = f"https://github.com/odoo/odoo-ls/releases/download/{RELEASE['version']}/{asset}"
            with urllib.request.urlopen(url, timeout=120) as response, download.open("wb") as output:
                shutil.copyfileobj(response, output)
            unpack_verified(download, destination, RELEASE["assets"][asset])
        binary = unpacked / workspace.binary.name
        binary.chmod(binary.stat().st_mode | 0o111)
        subprocess.run([str(binary), "--version"], check=True, capture_output=True)
        (unpacked / "installation.json").write_text(json.dumps(RELEASE, indent=2) + "\n")
        unpacked.rename(workspace.release)


def install_source(workspace: Workspace) -> None:
    revision = RELEASE["odoo_revision"]
    if workspace.source.exists():
        actual = subprocess.check_output(["git", "-C", str(workspace.source), "rev-parse", "HEAD"], text=True).strip()
        tracked = subprocess.check_output(
            [
                "git",
                "-C",
                str(workspace.source),
                "ls-tree",
                "-r",
                "--name-only",
                "HEAD",
                "--",
                "addons",
                "odoo/addons",
            ],
            text=True,
        ).splitlines()
        manifests = [path for path in tracked if path.endswith("/__manifest__.py")]
        if actual != revision or not manifests or any(not (workspace.source / path).is_file() for path in manifests):
            raise RuntimeError("Odoo mirror does not match the pin or lacks addons; move it aside and run setup again.")
        return
    with tempfile.TemporaryDirectory(dir=workspace.local) as staging:
        source = Path(staging) / "source"
        subprocess.run(["git", "init", "--quiet", str(source)], check=True)
        commands = [
            ["remote", "add", "origin", "https://github.com/odoo/odoo.git"],
            ["config", "remote.origin.promisor", "true"],
            ["config", "remote.origin.partialclonefilter", "blob:none"],
            ["sparse-checkout", "init", "--cone"],
            ["sparse-checkout", "set", "odoo", "addons"],
            ["fetch", "--quiet", "--depth", "1", "--filter=blob:none", "origin", revision],
            ["-c", "advice.detachedHead=false", "checkout", "--quiet", "--detach", "FETCH_HEAD"],
        ]
        for command in commands:
            subprocess.run(["git", "-C", str(source), *command], check=True)
        source.rename(workspace.source)


def install(root: Path) -> None:
    workspace = Workspace(root)
    workspace.local.mkdir(parents=True, exist_ok=True)
    with FileLock(str(workspace.local / "install.lock"), timeout=1200):
        install_release(workspace)
        install_source(workspace)
        from .prerequisites import install_terraform

        install_terraform(workspace)
    print(f"OdooLS {RELEASE['version']} and Odoo source ready in {workspace.local}.")
