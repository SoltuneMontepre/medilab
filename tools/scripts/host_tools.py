"""Portable host process and selected-endpoint helpers for local setup commands."""

import ipaddress
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[2]
URL_ERROR = "MEDILAB_URL must be a local HTTP(S) URL matching the saved Odoo port, without credentials, query or fragment."


class HostError(RuntimeError):
    pass


def assert_onlyoffice_engine(information):
    if isinstance(information, dict) and isinstance(information.get("host"), dict):
        return
    version = (
        information.get("ServerVersion") if isinstance(information, dict) else None
    )
    match = (
        re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:[-+][\w.~-]+)?", version)
        if isinstance(version, str)
        else None
    )
    if not match or int(match[1]) < 28:
        raise HostError(
            "Managed ONLYOFFICE requires Docker Engine server 28 or newer for isolated internal networking. "
            "Update the local Docker engine (Docker Desktop on Windows), or use the supported local Podman setup. "
            "The Docker CLI version alone does not establish server support."
        )


def check_node_version(value):
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", value)
    version = tuple(map(int, match.groups())) if match else ()
    if not version or not (
        (version[0] == 20 and version >= (20, 19, 0)) or version >= (22, 12, 0)
    ):
        raise HostError(
            "Vite 7 requires Node.js 20.19+ (20.x) or >=22.12, including npm/npx. Install a compatible release and reopen the terminal."
        )


def loopback_host(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except (ValueError, TypeError):
        return False


def executable(name, *, path=None):
    resolved = shutil.which(name, path=path)
    if not resolved:
        raise HostError(
            f"{name} was not found. Install the prerequisites in README.md and reopen your terminal."
        )
    return resolved


def process_arguments(argv, environment=None):
    arguments = [str(argument) for argument in argv]
    if not arguments:
        raise HostError("A host command is required.")
    environment = os.environ if environment is None else environment
    arguments[0] = executable(arguments[0], path=environment.get("PATH"))
    if os.name == "nt" and os.path.splitext(arguments[0])[1].lower() in {
        ".cmd",
        ".bat",
    }:
        # Batch launchers need cmd.exe. Reject expansion/operator syntax rather than interpreting it.
        if any(
            any(character in argument for character in '\r\n%!^&|<>"')
            for argument in arguments
        ):
            raise HostError(
                "This batch launcher cannot safely accept this path or argument. Use the native executable instead."
            )
        command = subprocess.list2cmdline(arguments)
        processor = subprocess.list2cmdline([environment.get("COMSPEC", "cmd.exe")])
        return f'{processor} /d /s /v:off /c "{command}"'
    return arguments


def run(argv, *, cwd=None, env=None, check=True, capture_output=False, timeout=None):
    try:
        return subprocess.run(
            process_arguments(argv, env),
            cwd=cwd,
            env=env,
            check=check,
            capture_output=capture_output,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except OSError as error:
        raise HostError(
            "The required host program could not be started. Check its installation and PATH."
        ) from error


def binding_matches(binding, port, hostname):
    if str(binding.get("HostPort")) != str(port):
        return False
    addresses = {"127.0.0.1", "::1"} if hostname == "localhost" else {hostname}
    published = binding.get("HostIp")
    for address in addresses:
        if published == address:
            return True
        version = ipaddress.ip_address(address).version
        if published == ("0.0.0.0" if version == 4 else "::"):
            return True
    return False


def verify_running_odoo(values, marker, port, hostname):
    from compose_env import project_name
    from demo_bootstrap import (
        OWNER_LABEL,
        PROJECT_LABEL,
        _assert_local_engine,
        _inspect,
        _labels,
    )
    from local_compose import _resolve

    project = project_name()
    if (
        not values.get("COMPOSE_PROJECT_NAME")
        or values["COMPOSE_PROJECT_NAME"] != project
    ):
        raise HostError(
            "A saved selection for this worktree is required. Run task setup before using the selected backend."
        )
    if marker is not None and marker.get("status") != "completed":
        raise HostError(
            "The selected local environment is not completed. Follow its setup/recovery guidance first."
        )
    if marker is not None and (
        not isinstance(marker.get("owner"), str) or not marker["owner"]
    ):
        raise HostError(
            "The completed environment's saved ownership identity is unavailable."
        )
    _assert_local_engine()
    resolved, _marker, _files, _environment = _resolve("ps")
    if resolved != project:
        raise HostError(
            "The runtime selection differs from this worktree's saved project."
        )
    candidates = [
        item
        for item in _inspect("ps", project)
        if _labels(item, "containers").get(PROJECT_LABEL) == project
        and _labels(item, "containers").get("com.docker.compose.service") == "odoo"
    ]
    if (
        len(candidates) != 1
        or candidates[0].get("State", {}).get("Running") is not True
    ):
        raise HostError(
            "The selected project's Odoo container is not uniquely running. Start that stack before verification."
        )
    container = candidates[0]
    if marker is not None and _labels(container, "containers").get(
        OWNER_LABEL
    ) != marker.get("owner"):
        raise HostError(
            "The running Odoo container does not match the saved environment owner."
        )
    bindings = (
        container.get("NetworkSettings", {}).get("Ports", {}).get("8069/tcp") or []
    )
    if not any(binding_matches(binding, port, hostname) for binding in bindings):
        raise HostError(
            "The running selected Odoo does not publish its 8069/tcp service on the saved local port."
        )


def _selected_url(values):
    try:
        port = int(values.get("MEDILAB_ODOO_PORT", "8069"))
        selected = values.get("MEDILAB_URL") or f"http://localhost:{port}"
        parsed = urlsplit(selected)
        actual_port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except (ValueError, TypeError, AttributeError) as error:
        raise HostError(URL_ERROR) from error
    if (
        not 1 <= port <= 65535
        or parsed.scheme not in {"http", "https"}
        or not loopback_host(parsed.hostname)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or actual_port != port
        or any(character.isspace() or ord(character) < 32 for character in selected)
        or "\\" in selected
    ):
        raise HostError(URL_ERROR)
    return port, parsed


def selected_odoo_url(*, require_saved_selection=False):
    from compose_env import project_name
    from demo_bootstrap import BootstrapError, _read_compose_env, _read_marker

    try:
        values = _read_compose_env()
        marker = _read_marker()
        if marker is not None:
            if marker.get("project") != project_name():
                raise HostError(
                    "The selected local environment belongs to another project."
                )
            config = marker.get("config") or {}
            if any(values.get(key) != value for key, value in config.items()):
                raise HostError(
                    "The saved local environment configuration does not match its ownership marker."
                )
            values = {**values, **config}
    except (
        BootstrapError,
        ValueError,
        TypeError,
        AttributeError,
        OSError,
        subprocess.CalledProcessError,
    ) as error:
        raise HostError(
            "The selected environment could not be read safely. Check its ownership marker and the setup recovery guidance."
        ) from error
    port, parsed = _selected_url(values)
    if require_saved_selection:
        try:
            verify_running_odoo(values, marker, port, parsed.hostname)
        except (
            BootstrapError,
            ValueError,
            TypeError,
            AttributeError,
            KeyError,
            OSError,
            subprocess.CalledProcessError,
        ) as error:
            raise HostError(
                "The selected running environment could not be verified safely. Check its ownership and local engine."
            ) from error
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
