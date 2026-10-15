"""Local prerequisites for Serena and an isolated Cursor profile."""

import hashlib
import platform
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from .install import unpack_verified
from .workspace import RELEASE, Workspace


def platform_target() -> tuple[str, str]:
    system = {"Linux": "linux", "Darwin": "darwin", "Windows": "win32"}.get(platform.system())
    architecture = {"x86_64": "x64", "AMD64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine())
    if not system or not architecture:
        raise ValueError("Unsupported tooling platform.")
    return system, architecture


def download(url: str, destination: Path, digest: str) -> None:
    with urllib.request.urlopen(url, timeout=120) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)
    if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
        destination.unlink()
        raise ValueError(f"SHA-256 mismatch for {destination.name}.")


def terraform_directory(workspace: Workspace) -> Path:
    return workspace.local / "terraform" / RELEASE["terraform"]["version"]


def install_terraform(workspace: Workspace) -> None:
    destination = terraform_directory(workspace)
    binary = destination / ("terraform.exe" if platform.system() == "Windows" else "terraform")
    if binary.is_file():
        return
    system, architecture = platform_target()
    system = "windows" if system == "win32" else system
    architecture = "amd64" if architecture == "x64" else architecture
    version = RELEASE["terraform"]["version"]
    asset = f"terraform_{version}_{system}_{architecture}.zip"
    with tempfile.TemporaryDirectory(dir=workspace.local) as staging:
        archive = Path(staging) / asset
        digest = RELEASE["terraform"]["assets"][asset]
        download(f"https://releases.hashicorp.com/terraform/{version}/{asset}", archive, digest)
        unpack_verified(archive, destination, digest)
    binary.chmod(binary.stat().st_mode | 0o111)
    actual = subprocess.check_output([str(binary), "version", "-json"], text=True)
    if f'"{version}"' not in actual:
        raise RuntimeError("Terraform binary does not match the pinned infrastructure version.")


def install_cursor(root: Path) -> None:
    cursor = shutil.which("cursor")
    if not cursor:
        raise RuntimeError("cursor not found. Install Cursor before running task ai:cursor-setup.")
    directory = root / ".local" / "cursor"
    directory.mkdir(parents=True, exist_ok=True)
    system, architecture = platform_target()
    if system == "linux" and platform.libc_ver()[0] != "glibc":
        system = "alpine"
    asset = f"odoo-{system}-{architecture}-{RELEASE['version']}.vsix"
    archive = directory / asset
    digest = RELEASE["editor_assets"][asset]
    if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        download(f"https://github.com/odoo/odoo-vscode/releases/download/{RELEASE['version']}/{asset}", archive, digest)
    subprocess.run(
        [
            cursor,
            "--user-data-dir",
            str(directory / "user-data"),
            "--extensions-dir",
            str(directory / "extensions"),
            "--install-extension",
            str(archive),
        ],
        check=True,
    )
