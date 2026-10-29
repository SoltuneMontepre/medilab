"""Owned local ONLYOFFICE state; importing this module never creates files or starts services."""

import base64
import hashlib
import hmac
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / ".local/onlyoffice"
OVERLAY = ROOT / "tools/onlyoffice/compose.yml"
SERVER_OVERLAY = ROOT / "src/applications/medilab-sync/docker-compose.yml"
OWNER_LABEL = "com.medilab.onlyoffice.owner"
VOLUME_KEYS = (
    "MEDILAB_ONLYOFFICE_LIB_VOLUME",
    "MEDILAB_ONLYOFFICE_DATA_VOLUME",
    "MEDILAB_ONLYOFFICE_FONTS_VOLUME",
)
CONFIG_KEYS = (*VOLUME_KEYS, "MEDILAB_ONLYOFFICE_PORT")
SERVICES = ("onlyoffice", "onlyoffice-adapter", "onlyoffice-gateway")
SERVER_IMAGE = "docker.io/onlyoffice/documentserver:9.4.0.1@sha256:3ab6ebc7c605e5a32b7ae3ff19daed4925090245acc8100ce2230bd766c88212"
INPUT_KEYS = (
    "ONLYOFFICE_JWT_SECRET",
    "ONLYOFFICE_INTERNAL_URL",
    "ONLYOFFICE_PUBLIC_URL",
    "ONLYOFFICE_CALLBACK_ORIGIN",
    "ONLYOFFICE_TLS_DIR",
    "ONLYOFFICE_CA_DIR",
    "ONLYOFFICE_PORT",
)

WINDOWS_ACL = r"""
$ErrorActionPreference='Stop'
Import-Module -Name (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
$p=$env:MEDILAB_ONLYOFFICE_ACL_PATH
$u=[Security.Principal.WindowsIdentity]::GetCurrent().User
if($env:MEDILAB_ONLYOFFICE_ACL_PROTECT -eq '1') {
  if(Test-Path -LiteralPath $p -PathType Container) {
    $a=New-Object Security.AccessControl.DirectorySecurity
    $flags=[Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'
  } else {
    $a=New-Object Security.AccessControl.FileSecurity
    $flags=[Security.AccessControl.InheritanceFlags]::None
  }
  $a.SetOwner($u)
  $a.SetAccessRuleProtection($true,$false)
  foreach($sid in @($u.Value,'S-1-5-18')) {
    $identity=New-Object Security.Principal.SecurityIdentifier($sid)
    $rule=New-Object Security.AccessControl.FileSystemAccessRule($identity,'FullControl',$flags,'None','Allow')
    $a.AddAccessRule($rule)
  }
  Set-Acl -LiteralPath $p -AclObject $a
}
$a=Get-Acl -LiteralPath $p
if(-not $a.AreAccessRulesProtected){exit 1}
if($a.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $u.Value){exit 1}
foreach($rule in $a.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])) {
  if($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Value -notin @($u.Value,'S-1-5-18')) {exit 1}
}
"""


def windows_acl(path, *, create=False):
    environment = dict(
        os.environ,
        MEDILAB_ONLYOFFICE_ACL_PATH=str(path),
        MEDILAB_ONLYOFFICE_ACL_PROTECT="1" if create else "0",
    )
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            base64.b64encode(WINDOWS_ACL.encode("utf-16-le")).decode("ascii"),
        ],
        env=environment,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise OnlyofficeError(
            "ONLYOFFICE private material requires a protected current-user/SYSTEM-only Windows ACL."
        )


class OnlyofficeError(RuntimeError):
    pass


def validated_port(value):
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        digits = value.lstrip("0") or "0"
        number = int(digits) if len(digits) <= 5 else 0
    elif isinstance(value, int) and not isinstance(value, bool):
        number = int(value)
    else:
        number = 0
    if not 1 <= number <= 65535:
        raise OnlyofficeError(
            "The saved ONLYOFFICE port is invalid; no resources were changed."
        )
    return number


def dotenv_value(raw):
    value = raw.strip()
    if value.startswith(("'", '"')):
        quote = value[0]
        end = value.find(quote, 1)
        if end < 0 or (
            value[end + 1 :].strip() and not value[end + 1 :].strip().startswith("#")
        ):
            raise OnlyofficeError(
                "The explicit ONLYOFFICE configuration has invalid dotenv quoting; no value was replaced."
            )
        return value[1:end]
    return re.split(r"\s+#", value, maxsplit=1)[0].rstrip()


def configuration_inputs(environment, *, fresh=False):
    sources = [dict(environment)]
    if not fresh:
        for file in (ROOT / "src/core/.env.local", ROOT / "tools/infrastructure/.env"):
            if not file.exists():
                continue
            for line in file.read_text(encoding="utf-8-sig").splitlines():
                assignment = line.strip().removeprefix("export ")
                key, separator, value = assignment.partition("=")
                if separator and key.strip() in INPUT_KEYS:
                    sources.append({key.strip(): dotenv_value(value)})
    result = {}
    for source in sources:
        for key in INPUT_KEYS:
            if key not in source:
                continue
            value = source[key]
            if key != "ONLYOFFICE_JWT_SECRET" and value == "":
                continue
            if not isinstance(value, str) or (
                key == "ONLYOFFICE_JWT_SECRET"
                and not re.fullmatch(r"[A-Za-z0-9_-]{32,}", value)
            ):
                raise OnlyofficeError(
                    "The explicit ONLYOFFICE JWT configuration is invalid; it will not be replaced with a generated secret."
                )
            if key in result and not hmac.compare_digest(
                result[key].encode(), value.encode()
            ):
                raise OnlyofficeError(
                    "Explicit ONLYOFFICE configuration sources conflict; no value was selected or replaced."
                )
            result[key] = value
    return result


def expected_configuration(state):
    directory = state_directory(state["project"], state.get("base_owner"))
    result = {
        "ONLYOFFICE_INTERNAL_URL": "https://onlyoffice-gateway:9443",
        "ONLYOFFICE_PUBLIC_URL": f"http://localhost:{state['config']['MEDILAB_ONLYOFFICE_PORT']}",
        "ONLYOFFICE_CALLBACK_ORIGIN": "https://onlyoffice-gateway:7443",
        "ONLYOFFICE_TLS_DIR": (directory / "tls/server").as_posix(),
        "ONLYOFFICE_CA_DIR": (directory / "tls/public").as_posix(),
        "ONLYOFFICE_PORT": state["config"]["MEDILAB_ONLYOFFICE_PORT"],
    }
    file = checked_path(directory / "jwt", private=True)
    if file.exists():
        value = file.read_text(encoding="ascii").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,}", value):
            raise OnlyofficeError(
                "The owned JWT identity is invalid; automatic replacement is refused."
            )
        result["ONLYOFFICE_JWT_SECRET"] = value
    elif state.get("material"):
        raise OnlyofficeError(
            "The owned JWT identity is missing; automatic replacement is refused."
        )
    if state.get("material") and state["material"] != material_fingerprints(directory):
        raise OnlyofficeError(
            "Owned editing-service material changed; preserve it and inspect the selected local configuration."
        )
    return result


def assert_configuration_matches(provided, expected):
    for key, value in provided.items():
        if key in {"ONLYOFFICE_TLS_DIR", "ONLYOFFICE_CA_DIR"}:
            matches = (
                key in expected
                and isinstance(value, str)
                and os.path.normcase(os.path.abspath(value))
                == os.path.normcase(os.path.abspath(expected[key]))
            )
            if matches:
                checked_path(Path(expected[key]))
        else:
            matches = (
                key in expected
                and isinstance(value, str)
                and hmac.compare_digest(value.encode(), expected[key].encode())
            )
        if not matches:
            raise OnlyofficeError(
                "Existing editing-service configuration differs from the managed selection. Preserve it and use its existing maintenance workflow or a separate isolated demo; automatic migration is refused."
            )


def optional_volume_names(config):
    present = [key in config for key in CONFIG_KEYS]
    if any(present) and not all(present):
        raise OnlyofficeError(
            "The ONLYOFFICE identity extension is incomplete; run onlyoffice:setup to recover its registration."
        )
    return {config[key] for key in VOLUME_KEYS} if all(present) else set()


def verify_registration(state, marker, persisted):
    if not state.get("registered") or any(
        persisted.get(key) != value for key, value in state["config"].items()
    ):
        raise OnlyofficeError(
            "The ONLYOFFICE registration does not match this selected environment; recover its journal first."
        )
    if marker and any(
        marker["config"].get(key) != value for key, value in state["config"].items()
    ):
        raise OnlyofficeError(
            "The ONLYOFFICE registration differs from the base ownership marker."
        )


def checked_path(path, *, private=False):
    path = Path(path)
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
            raise OnlyofficeError(
                "ONLYOFFICE paths must not contain symbolic links or junctions."
            )
    if path.exists() and os.name != "nt":
        info = path.stat()
        if info.st_uid != os.getuid() or (
            private and stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise OnlyofficeError(
                "ONLYOFFICE private material must belong to the current user and refuse other users."
            )
    if path.exists() and private and os.name == "nt":
        windows_acl(path)
    return path


def protect(path):
    path = checked_path(path)
    if os.name == "nt":
        windows_acl(path, create=True)
    else:
        path.chmod(0o700 if path.is_dir() else 0o600)


def atomic_json(path, value):
    path = checked_path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, sort_keys=True, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        Path(temporary).replace(path)
        protect(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def state_directory(project, base_owner=None):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,100}", project):
        raise OnlyofficeError("The selected Compose project identity is invalid.")
    generation = (
        hashlib.sha256(base_owner.encode()).hexdigest()[:16]
        if base_owner
        else "ordinary"
    )
    return checked_path(DIRECTORY / project / generation)


def _validate_state(value):
    error = "The owned ONLYOFFICE state is invalid; no resources were changed."
    if (
        not isinstance(value, dict)
        or type(value.get("format")) is not int
        or value["format"] != 1
    ):
        raise OnlyofficeError(error)
    owner = value.get("owner")
    config = value.get("config")
    status = value.get("status")
    if (
        not isinstance(owner, str)
        or not re.fullmatch(r"[a-f0-9]{32}", owner)
        or not isinstance(config, dict)
        or set(config) != set(CONFIG_KEYS)
        or not isinstance(status, str)
        or status not in {"preparing", "completed"}
        or not isinstance(value.get("engine"), str)
        or not value["engine"]
    ):
        raise OnlyofficeError(error)
    if (
        not isinstance(config["MEDILAB_ONLYOFFICE_PORT"], str)
        or type(value.get("http_port")) is not int
    ):
        raise OnlyofficeError(error)
    validated_port(config["MEDILAB_ONLYOFFICE_PORT"])
    validated_port(value["http_port"])
    for key, kind in zip(VOLUME_KEYS, ("lib", "data", "fonts"), strict=True):
        if config[key] != f"{value.get('project')}_onlyoffice_{kind}_{owner[:12]}":
            raise OnlyofficeError(error)
    if "provider" in value or status == "completed":
        provider = value.get("provider")
        if not isinstance(provider, str) or provider not in {"docker", "podman"}:
            raise OnlyofficeError(error)
    if "registered" in value and type(value["registered"]) is not bool:
        raise OnlyofficeError(error)
    if "material" in value:
        material = value["material"]
        if (
            not isinstance(material, dict)
            or set(material) != {"jwt", "tls/public/ca.crt", "tls/server/tls.crt"}
            or any(
                not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
                for digest in material.values()
            )
        ):
            raise OnlyofficeError(error)


def read_state(project, marker=None, engine=None):
    directory = state_directory(project, (marker or {}).get("owner"))
    file = checked_path(directory / "state.json", private=True)
    if not file.exists():
        return None
    checked_path(directory, private=True)
    try:
        value = json.loads(file.read_text(encoding="utf-8"))
    except (ValueError, OSError) as error:
        raise OnlyofficeError(
            "Cannot read the owned ONLYOFFICE state; no resources were changed."
        ) from error
    _validate_state(value)
    if (
        value.get("format") != 1
        or value.get("project") != project
        or value.get("worktree") != str(ROOT)
    ):
        raise OnlyofficeError(
            "The ONLYOFFICE state belongs to another selection or worktree."
        )
    if value.get("base_owner") != (marker or {}).get("owner"):
        raise OnlyofficeError(
            "The ONLYOFFICE state belongs to another bootstrap generation."
        )
    if engine is not None and value.get("engine") != engine:
        raise OnlyofficeError(
            "The selected engine differs from the owned ONLYOFFICE engine."
        )
    return value


def material_fingerprints(directory):
    return {
        name: hashlib.sha256(
            checked_path(directory / name, private=name == "jwt").read_bytes()
        ).hexdigest()
        for name in ("jwt", "tls/public/ca.crt", "tls/server/tls.crt")
    }


def runtime_environment(state, environment):
    directory = state_directory(state["project"], state.get("base_owner"))
    checked_path(directory / "jwt", private=True)
    checked_path(directory / "tls/ca.key", private=True)
    secret = (directory / "jwt").read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,}", secret):
        raise OnlyofficeError(
            "The saved ONLYOFFICE JWT identity is invalid; it will not be replaced."
        )
    if "ONLYOFFICE_JWT_SECRET" in environment and not hmac.compare_digest(
        secret.encode(), str(environment["ONLYOFFICE_JWT_SECRET"]).encode()
    ):
        raise OnlyofficeError(
            "The provided JWT differs from the owned secret; neither identity was rotated."
        )
    if state.get("material") != material_fingerprints(directory):
        raise OnlyofficeError(
            "The saved ONLYOFFICE secret or certificate identity changed; it will not be silently rotated."
        )
    for relative in (
        "tls/server/tls.crt",
        "tls/server/tls.key",
        "tls/public/ca.crt",
        "tls/public/bundle.crt",
        "runtime.json",
    ):
        file = checked_path(directory / relative, private=relative.endswith(".key"))
        if not file.is_file():
            raise OnlyofficeError(
                "Completed ONLYOFFICE material is missing; it will not be regenerated."
            )
    return {
        **environment,
        **state["config"],
        "ONLYOFFICE_PORT": state["config"]["MEDILAB_ONLYOFFICE_PORT"],
        "ONLYOFFICE_STATE_DIR": directory.as_posix(),
        "ONLYOFFICE_SOURCE_ROOT": ROOT.as_posix(),
        "ONLYOFFICE_TLS_DIR": (directory / "tls/server").as_posix(),
        "ONLYOFFICE_CA_DIR": (directory / "tls/public").as_posix(),
        "ONLYOFFICE_JWT_SECRET": secret,
        "MEDILAB_ONLYOFFICE_OWNER": state["owner"],
        "MEDILAB_ONLYOFFICE_BASE_OWNER": state.get("base_owner") or "",
        "ONLYOFFICE_HTTP_PORT": str(state["http_port"]),
        "ONLYOFFICE_CONTAINER_PORT": str(state["http_port"]),
    }


def missing_core_volumes(config, missing):
    return sorted(set(missing) - optional_volume_names(config))


def network_driver_options(provider):
    if provider == "podman":
        return {"isolate": "strict"}
    if provider == "docker":
        return {
            f"com.docker.network.bridge.gateway_mode_ipv{version}": "isolated"
            for version in (4, 6)
        }
    raise OnlyofficeError("The editor network provider has not been verified.")


def assert_network_policy(network, provider):
    if network.get("Driver", network.get("driver")) != "bridge":
        raise OnlyofficeError(
            "The owned editor network is not a verified bridge network."
        )
    if not network.get("Internal", network.get("internal", False)):
        raise OnlyofficeError("The ONLYOFFICE network is not internal.")
    options = network.get("Options") or network.get("options") or {}
    if any(
        options.get(key) != value
        for key, value in network_driver_options(provider).items()
    ):
        raise OnlyofficeError(
            "The owned editor network isolation policy is missing; preserve it for explicit recovery."
        )


def resolve_addon(project, marker, environment, operation):
    try:
        state = read_state(project, marker)
    except (OnlyofficeError, OSError, ValueError):
        if operation in {"up", "stop", "down", "logs", "ps", "restart", "run", "exec"}:
            print(
                "ONLYOFFICE ownership requires recovery; continuing with base services only.",
                file=sys.stderr,
            )
            return [], {}
        raise
    if not state:
        return [], {}
    if state.get("status") != "completed":
        print(
            "ONLYOFFICE preparation is incomplete; continuing with base services only.",
            file=sys.stderr,
        )
        return [], {}
    try:
        from demo_bootstrap import (
            _assert_local_engine,
            _labels,
            _read_compose_env,
            _resources,
        )

        verify_registration(state, marker, _read_compose_env())
        if state.get("engine") != _assert_local_engine():
            raise OnlyofficeError("The ONLYOFFICE engine has changed.")
        resources = _resources(project)
        volumes = {
            item.get("Name") or item.get("name"): item for item in resources["volumes"]
        }
        for name in optional_volume_names(state["config"]):
            if (
                name not in volumes
                or _labels(volumes[name], "volumes").get(OWNER_LABEL) != state["owner"]
            ):
                raise OnlyofficeError(
                    "Owned ONLYOFFICE persistent storage is missing or foreign."
                )
        networks = [
            item
            for item in resources["networks"]
            if (item.get("Name") or item.get("name")) == project + "_onlyoffice"
        ]
        if (
            len(networks) != 1
            or _labels(networks[0], "networks").get(OWNER_LABEL) != state["owner"]
            or not networks[0].get("Internal", networks[0].get("internal", False))
        ):
            raise OnlyofficeError(
                "The owned internal editor network is missing; use onlyoffice:up to restore its policy."
            )
        assert_network_policy(networks[0], state.get("provider"))
        configured = runtime_environment(state, environment)
    except (OnlyofficeError, OSError):
        if operation not in {
            "up",
            "stop",
            "down",
            "logs",
            "ps",
            "restart",
            "run",
            "exec",
        }:
            raise
        print(
            "ONLYOFFICE material or storage is unavailable; continuing with base services only.",
            file=sys.stderr,
        )
        return [], {}
    files = ["-f", str(SERVER_OVERLAY), "-f", str(OVERLAY)]
    if state.get("base_owner"):
        files += ["-f", str(ROOT / "tools/onlyoffice/compose.owned.yml")]
    return files, configured
