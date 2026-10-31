"""Check native MediLab Sync build prerequisites without installing tools or opening a user profile."""

import os
import pathlib
import platform
import re
import shutil
import subprocess
import tempfile

from host_tools import HostError, check_node_version, executable, run

ROOT = pathlib.Path(__file__).resolve().parents[2]
PREREQUISITES = "https://v2.tauri.app/start/prerequisites/"
WEBVIEW_CLIENT = (
    r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
)


def linux_family(release=None):
    values = platform.freedesktop_os_release() if release is None else release
    identifiers = {values.get("ID", ""), *values.get("ID_LIKE", "").split()}
    for family in ("arch", "debian", "ubuntu", "fedora", "rhel"):
        if family in identifiers:
            return family
    return "linux"


def linux_instructions(family):
    if family == "arch":
        return "Install with pacman: base-devel pkgconf webkit2gtk-4.1 libappindicator-gtk3 librsvg xdotool xdg-utils dbus."
    if family in {"debian", "ubuntu"}:
        return (
            "Install build-essential pkg-config libwebkit2gtk-4.1-dev libayatana-appindicator3-dev "
            "librsvg2-dev libxdo-dev libdbus-1-dev xdg-utils."
        )
    if family in {"fedora", "rhel"}:
        return (
            "Install gcc gcc-c++ make pkgconf-pkg-config webkit2gtk4.1-devel "
            "libappindicator-gtk3-devel librsvg2-devel libxdo-devel dbus-devel xdg-utils."
        )
    return f"Install your distribution's Tauri 2 development libraries: {PREREQUISITES}"


def _version(name, args):
    instructions = {
        "bun": "Install Bun from https://bun.sh/docs/installation and reopen the terminal.",
        "node": "Install native Node.js LTS and reopen the terminal.",
        "cargo": "Install Rust with rustup and add rustfmt/clippy for the selected toolchain.",
        "rustc": "Install native Rust with rustup; use the MSVC toolchain on Windows.",
    }
    try:
        return run(
            [executable(name), *args], cwd=ROOT, capture_output=True, timeout=30
        ).stdout.strip()
    except (HostError, subprocess.CalledProcessError) as error:
        raise HostError(
            f"Sync requires working {name} {' '.join(args)}. {instructions[name]}"
        ) from error


def check_bun_version(value):
    lockfile = ROOT / "src/applications/medilab-sync/bun.lock"
    try:
        formats = re.findall(
            r'"lockfileVersion"\s*:\s*(\d+)', lockfile.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError) as error:
        raise HostError(
            "Sync requires its committed bun.lock to check Bun compatibility."
        ) from error
    if formats != ["2"]:
        raise HostError(
            "Unsupported Sync bun.lock format. Review the committed lockfile and Bun compatibility."
        )
    version = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:\+[\w.-]+)?", value)
    # Bun 1.4 introduced lockfileVersion 2: https://bun.com/blog/bun-v1.4
    if not version or tuple(int(part) for part in version.groups()) < (1, 4, 0):
        raise HostError(
            f"Bun {value} cannot read the committed Sync lockfileVersion 2. "
            "Sync requires stable Bun >=1.4.0. Install a compatible Bun from https://bun.sh/docs/installation "
            "and reopen the terminal; keep bun.lock unchanged."
        )


def check_linux():
    instructions = linux_instructions(linux_family())
    for name in ("cc", "pkg-config", "xdg-open"):
        if not shutil.which(name):
            raise HostError(f"Sync requires {name}. {instructions}")
    for package in ("webkit2gtk-4.1", "gtk+-3.0", "dbus-1", "librsvg-2.0"):
        result = run(
            [executable("pkg-config"), "--exists", package],
            check=False,
            capture_output=True,
            timeout=30,
        )
        if result.returncode:
            raise HostError(f"Sync cannot find {package}. {instructions}")
    indicators = ("appindicator3-0.1", "ayatana-appindicator3-0.1")
    if all(
        run(
            [executable("pkg-config"), "--exists", name],
            check=False,
            capture_output=True,
            timeout=30,
        ).returncode
        for name in indicators
    ):
        raise HostError(f"Sync requires a GTK3 appindicator library. {instructions}")


def webview_version(registry=None):
    if registry is None:
        import winreg as registry

    for hive in (registry.HKEY_LOCAL_MACHINE, registry.HKEY_CURRENT_USER):
        for view in (registry.KEY_WOW64_32KEY, registry.KEY_WOW64_64KEY):
            try:
                with registry.OpenKey(
                    hive, WEBVIEW_CLIENT, 0, registry.KEY_READ | view
                ) as key:
                    version, _kind = registry.QueryValueEx(key, "pv")
                if (
                    isinstance(version, str)
                    and re.fullmatch(r"\d+(?:\.\d+){3}", version)
                    and any(int(part) for part in version.split("."))
                ):
                    return version
            except OSError:
                continue
    return None


def check_windows(rust_info):
    host = re.search(r"^host:\s*(\S+)", rust_info, re.MULTILINE)
    if not host or not host[1].endswith("-windows-msvc"):
        raise HostError(
            "Sync requires native MSVC Rust on Windows. Install Rust stable-msvc; GNU/WSL targets are not supported here."
        )
    finder = shutil.which("vswhere")
    if not finder:
        for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES", "PROGRAMW6432"):
            directory = os.environ.get(variable)
            if not directory:
                continue
            installation = (
                pathlib.Path(directory)
                / "Microsoft Visual Studio/Installer/vswhere.exe"
            )
            if installation.is_file():
                finder = str(installation)
                break
    if not finder:
        raise HostError(
            "Microsoft C++ Build Tools could not be located from PATH or Windows Program Files variables. "
            "Install Desktop development with C++, MSVC and a Windows SDK, then reopen PowerShell."
        )
    component = (
        "Microsoft.VisualStudio.Component.VC.Tools.ARM64"
        if host[1].startswith("aarch64-")
        else "Microsoft.VisualStudio.Component.VC.Tools.x86.x64"
    )
    result = run(
        [
            finder,
            "-latest",
            "-products",
            "*",
            "-requires",
            component,
            "-property",
            "installationPath",
        ],
        capture_output=True,
        timeout=30,
    )
    if not result.stdout.strip():
        raise HostError(
            "Microsoft C++ Build Tools are incomplete. Add Desktop development with C++, MSVC and a Windows SDK."
        )
    if not webview_version():
        raise HostError(
            "Sync requires Microsoft Edge WebView2 Runtime. Install its Evergreen Runtime, then reopen PowerShell."
        )


def link_probe():
    with tempfile.TemporaryDirectory(prefix="medilab-sync-link-") as temporary:
        directory = pathlib.Path(temporary)
        source = directory / "probe.rs"
        source.write_text("fn main() {}\n", encoding="utf-8")
        result = run(
            [executable("rustc"), str(source), "-o", str(directory / "probe.exe")],
            capture_output=True,
            check=False,
            timeout=60,
        )
        if result.returncode:
            raise HostError(
                "Rust could not link a native executable. Install the native compiler/linker and Windows SDK or Linux build libraries."
            )


def check_gui():
    if platform.system() == "Linux":
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            raise HostError(
                "Sync dev requires a native graphical desktop session (DISPLAY or WAYLAND_DISPLAY)."
            )
        if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
            raise HostError(
                "Sync dev requires a desktop D-Bus session and an unlocked Secret Service credential store."
            )


def doctor(*, link=True, gui=False):
    system = platform.system()
    if system not in {"Linux", "Windows"}:
        raise HostError(
            "These Sync tasks support native Linux and Windows. macOS setup is outside this workflow."
        )
    bun = _version("bun", ["--version"])
    check_bun_version(bun)
    versions = {
        "Bun": bun,
        "Node": _version("node", ["--version"]),
        "Cargo": _version("cargo", ["--version"]),
    }
    check_node_version(versions["Node"])
    rust_info = _version("rustc", ["--version", "--verbose"])
    _version("cargo", ["fmt", "--version"])
    _version("cargo", ["clippy", "--version"])
    if system == "Windows":
        check_windows(rust_info)
    else:
        check_linux()
    if link:
        link_probe()
    if gui:
        check_gui()
    return versions
