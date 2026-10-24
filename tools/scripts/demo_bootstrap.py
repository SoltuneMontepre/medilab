"""Create or verify the isolated local Compose project used by fresh demo setup.

Usage: python tools/scripts/demo_bootstrap.py setup|recover
The recovery command only removes resources whose Compose project and bootstrap owner labels match the local marker.
"""

import json
import os
import re
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

from compose_env import project_name

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "tools/infrastructure/docker-compose.yml"
OWNED_COMPOSE = ROOT / "tools/infrastructure/docker-compose.owned.yml"
BOOTSTRAP_COMPOSE = ROOT / "tools/infrastructure/docker-compose.bootstrap.yml"
COMPOSE_ENV_FILE = ROOT / "tools/infrastructure/.env"
ODOO_LOG_PRESENTER = ROOT / "tools/scripts/colorize_odoo_logs.py"
SET_COUNTRY_SCRIPT = ROOT / "tools/scripts/demo_bootstrap_set_country.py"
ACCOUNTING_SCRIPT = ROOT / "tools/scripts/demo_bootstrap_accounting.py"
MARKER = ROOT / ".local/demo-bootstrap.json"
SELECTIONS = ROOT / ".local/demo-bootstrap-selections"
SWITCH_JOURNAL = ROOT / ".local/demo-bootstrap-switch.json"
OWNER_LABEL = "com.medilab.bootstrap.owner"
PROJECT_LABEL = "com.docker.compose.project"
DATABASE = "medilab"
ODOO_CONFIG_ARGUMENT = "--config=/etc/odoo/odoo.conf"
ODOO_NO_CRON_ARGUMENT = "--max-cron-threads=0"
ODOO_DATABASE_ARGUMENTS = (
    "--db_host=postgres",
    "--db_port=5432",
    "--db_user=root",
    "--db_password=root",
)
INTERRUPTED_SWITCH_ERROR = (
    "An interrupted project switch exists; run `task setup:fresh:switch:recover`."
)
MODULES = [
    line.strip()
    for line in (ROOT / "src/core/modules.txt").read_text().splitlines()
    if line.strip()
]


class BootstrapError(RuntimeError):
    pass


def _is_local_engine_endpoint(endpoint):
    parsed = urlsplit(endpoint)
    if parsed.scheme in ("unix", "npipe"):
        return True
    return parsed.scheme == "tcp" and parsed.hostname in (
        "localhost",
        "127.0.0.1",
        "::1",
    )


def _assert_local_context(context, source):
    result = _run(
        ["docker", "context", "inspect", context],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise BootstrapError(
            "Could not verify that the selected container context is local."
        )
    host = json.loads(result.stdout)[0]["Endpoints"]["docker"]["Host"]
    if not _is_local_engine_endpoint(host):
        raise BootstrapError(
            f"The {source} container context is not local; refusing fresh bootstrap."
        )


def _assert_local_engine():
    endpoint = os.environ.get("DOCKER_HOST")
    context = os.environ.get("DOCKER_CONTEXT")
    if endpoint and not _is_local_engine_endpoint(endpoint):
        raise BootstrapError(
            "The configured container engine is not local; refusing fresh bootstrap."
        )
    if context:
        _assert_local_context(context, "configured")
    elif not endpoint:
        result = _run(["docker", "context", "show"], capture_output=True, check=False)
        if result.returncode == 0:
            _assert_local_context(result.stdout.strip(), "selected")
        else:
            version = _run(["docker", "--version"], capture_output=True, check=False)
            if "podman" not in version.stdout.lower():
                raise BootstrapError(
                    "Could not verify that the selected container engine is local."
                )


def _read_marker():
    if not MARKER.exists():
        return None
    try:
        return json.loads(MARKER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BootstrapError(
            f"Cannot read the local bootstrap ownership marker at {MARKER}."
        ) from error


def _write_marker(marker):
    MARKER.parent.mkdir(parents=True, exist_ok=True)
    temporary = MARKER.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(marker, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(MARKER)


def _read_compose_env():
    if not COMPOSE_ENV_FILE.exists():
        return {}
    values = {}
    for line in COMPOSE_ENV_FILE.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _write_compose_env(values):
    lines = (
        COMPOSE_ENV_FILE.read_text(encoding="utf-8").splitlines()
        if COMPOSE_ENV_FILE.exists()
        else []
    )
    pending = dict(values)
    output = []
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            output.append(line)
            continue
        key, _value = line.split("=", 1)
        if key in pending:
            output.append(f"{key}={pending.pop(key)}")
        else:
            output.append(line)
    output.extend(f"{key}={value}" for key, value in sorted(pending.items()))
    COMPOSE_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = COMPOSE_ENV_FILE.with_suffix(".tmp")
    temporary.write_text(
        "\n".join(output) + "\n",
        encoding="utf-8",
    )
    temporary.replace(COMPOSE_ENV_FILE)


def _fresh_config(project, owner, selected_ports=None):
    current = _read_compose_env()
    ports = {
        "MEDILAB_ODOO_PORT": current.get("MEDILAB_ODOO_PORT", "8069"),
        "MEDILAB_DB_PORT": current.get("MEDILAB_DB_PORT", "15432"),
        "MEDILAB_GARAGE_PORT": current.get("MEDILAB_GARAGE_PORT", "3900"),
        "MEDILAB_GARAGE_ADMIN_PORT": current.get("MEDILAB_GARAGE_ADMIN_PORT", "3903"),
        "MEDILAB_CLOUDBEAVER_PORT": current.get("MEDILAB_CLOUDBEAVER_PORT", "8978"),
    }
    for key, default in ports.items():
        value = selected_ports[key] if selected_ports else os.environ.get(key, default)
        try:
            port = int(value)
        except ValueError as error:
            raise BootstrapError(f"{key} must be a valid TCP port.") from error
        if not 1 <= port <= 65535:
            raise BootstrapError(f"{key} must be between 1 and 65535.")
        ports[key] = str(port)
    suffix = owner.split("-", 1)[0]
    volumes = {
        "MEDILAB_DB_VOLUME": f"{project}_db_{suffix}",
        "MEDILAB_GARAGE_VOLUME": f"{project}_garage_{suffix}",
        "MEDILAB_APP_VOLUME": f"{project}_app_{suffix}",
        "MEDILAB_CLOUDBEAVER_VOLUME": f"{project}_cloudbeaver_{suffix}",
    }
    return {
        **ports,
        **volumes,
        "COMPOSE_PROJECT_NAME": project,
        "MEDILAB_DEMO_BOOTSTRAP_OWNER": owner,
        "MEDILAB_ODOO_IMAGE": f"localhost/{project}-odoo:{suffix}",
    }


def _free_ports():
    keys = (
        "MEDILAB_ODOO_PORT",
        "MEDILAB_DB_PORT",
        "MEDILAB_GARAGE_PORT",
        "MEDILAB_GARAGE_ADMIN_PORT",
        "MEDILAB_CLOUDBEAVER_PORT",
    )
    probes = []
    try:
        for _key in keys:
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            probe.bind(("0.0.0.0", 0))
            probes.append(probe)
        return {
            key: str(probe.getsockname()[1])
            for key, probe in zip(keys, probes, strict=True)
        }
    finally:
        for probe in probes:
            probe.close()


def select(project):
    if not re.fullmatch(r"medilab-bootstrap-[a-z0-9][a-z0-9_-]{0,39}", project):
        raise BootstrapError(
            "Use a new project name beginning with medilab-bootstrap- and containing only lowercase letters, digits, _ or -."
        )
    _assert_local_engine()
    if SWITCH_JOURNAL.exists():
        raise BootstrapError(INTERRUPTED_SWITCH_ERROR)
    existing = _read_marker()
    if existing:
        if (
            existing.get("project") != project
            or not existing.get("selected_project")
            or existing.get("worktree") != str(ROOT)
            or existing.get("lifecycle_version") != 2
            or existing.get("status") not in ("selected", "completed")
            or (
                existing.get("status") == "completed"
                and existing.get("handoff_verified") is not True
            )
        ):
            raise BootstrapError(
                "This worktree already has a different or incomplete fresh bootstrap; refusing to replace its ownership marker."
            )
        config = existing["config"]
        persisted = _read_compose_env()
        if any(persisted.get(key) != value for key, value in config.items()):
            raise BootstrapError(
                "The saved Compose selection differs from .env; refusing to select an ambiguous environment."
            )
        if existing["status"] == "selected":
            _assert_no_resources(project)
        else:
            expected = {
                config[key]
                for key in (
                    "MEDILAB_DB_VOLUME",
                    "MEDILAB_GARAGE_VOLUME",
                    "MEDILAB_APP_VOLUME",
                    "MEDILAB_CLOUDBEAVER_VOLUME",
                )
            }
            if set(_owned_volume_names(project, existing["owner"])) != expected:
                raise BootstrapError(
                    "The selected project's persistent volumes do not match its ownership marker."
                )
        print(f"Compose project {project} is already selected ({existing['status']}).")
        return
    _assert_no_resources(project)
    owner = str(uuid.uuid4())
    config = _fresh_config(project, owner, _free_ports())
    _assert_ports_available(config)
    marker = {
        "database": DATABASE,
        "config": config,
        "lifecycle_version": 2,
        "owner": owner,
        "project": project,
        "selected_project": True,
        "status": "selected",
        "worktree": str(ROOT),
    }
    _write_marker(marker)
    _write_compose_env(config)
    print(
        f"Selected empty Compose project {project}. Odoo port: {config['MEDILAB_ODOO_PORT']}."
    )


def _validate_completed_selection(marker, project):
    if (
        not marker
        or marker.get("project") != project
        or marker.get("worktree") != str(ROOT)
        or marker.get("selected_project") is not True
        or marker.get("lifecycle_version") != 2
        or marker.get("status") != "completed"
        or marker.get("handoff_verified") is not True
    ):
        raise BootstrapError(
            f"Compose project {project!r} has no verified completed selection; refusing to switch."
        )
    config = marker["config"]
    if config.get("COMPOSE_PROJECT_NAME") != project:
        raise BootstrapError(
            "The saved Compose project identity does not match its marker."
        )
    if not marker.get("owner"):
        raise BootstrapError("A completed Compose selection has no owner UUID.")
    return config


def _verify_completed_selection(marker, project):
    config = _validate_completed_selection(marker, project)
    _assert_owned_resources(project, marker["owner"])
    expected = {
        config[key]
        for key in (
            "MEDILAB_DB_VOLUME",
            "MEDILAB_GARAGE_VOLUME",
            "MEDILAB_APP_VOLUME",
            "MEDILAB_CLOUDBEAVER_VOLUME",
        )
    }
    if set(_owned_volume_names(project, marker["owner"])) != expected:
        raise BootstrapError(
            "Owned persistent volumes do not match the saved Compose selection."
        )


def _read_selection_file(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BootstrapError(f"Cannot read saved selection {path}.") from error


def _saved_selection(project):
    paths = [
        SELECTIONS / f"{project}.json",
        *sorted(SELECTIONS.glob(f"{project}.*.json")),
    ]
    candidates = {}
    for path in paths:
        if not path.exists():
            continue
        marker = _read_selection_file(path)
        _validate_completed_selection(marker, project)
        owner = marker["owner"]
        if owner in candidates and candidates[owner] != marker:
            raise BootstrapError(
                "Archived selections conflict for the same owner UUID."
            )
        candidates[owner] = marker
    if not candidates:
        return None
    verified = []
    for marker in candidates.values():
        try:
            _verify_completed_selection(marker, project)
        except BootstrapError:
            continue
        verified.append(marker)
    if len(verified) != 1:
        raise BootstrapError(
            f"Compose project {project!r} has no unique resource-verified archived selection."
        )
    return verified[0]


def _archive_current_selection(marker):
    project = marker["project"]
    primary = SELECTIONS / f"{project}.json"
    path = primary
    if primary.exists():
        saved = _read_selection_file(primary)
        _validate_completed_selection(saved, project)
        if saved == marker:
            return
        if saved["owner"] == marker["owner"]:
            raise BootstrapError(
                "The archived selection conflicts with its owner UUID."
            )
        try:
            owner = str(uuid.UUID(marker["owner"]))
        except (ValueError, AttributeError) as error:
            raise BootstrapError(
                "The current selection has an invalid owner UUID."
            ) from error
        if owner != marker["owner"]:
            raise BootstrapError("The current selection has a noncanonical owner UUID.")
        path = SELECTIONS / f"{project}.{owner}.json"
    if path.exists():
        if _read_selection_file(path) != marker:
            raise BootstrapError(
                "The saved owner generation differs from the current selection."
            )
        return
    SELECTIONS.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        json.dump(marker, output, indent=2, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def _write_switch_journal(current, target):
    SWITCH_JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    try:
        with SWITCH_JOURNAL.open("x", encoding="utf-8") as output:
            json.dump({"from": current, "to": target}, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError as error:
        raise BootstrapError(INTERRUPTED_SWITCH_ERROR) from error


def switch(project):
    if not re.fullmatch(r"medilab-bootstrap-[a-z0-9][a-z0-9_-]{0,39}", project):
        raise BootstrapError(
            "Use a medilab-bootstrap- project name to switch selections."
        )
    _assert_local_engine()
    if SWITCH_JOURNAL.exists():
        raise BootstrapError(INTERRUPTED_SWITCH_ERROR)
    current = _read_marker()
    if not current:
        raise BootstrapError("No completed selection exists in this worktree.")
    current_project = current.get("project")
    _verify_completed_selection(current, current_project)
    persisted = _read_compose_env()
    if any(persisted.get(key) != value for key, value in current["config"].items()):
        raise BootstrapError("Current Compose configuration differs from its marker.")
    if project == current_project:
        print(f"Compose project {project} is already selected.")
        return

    target = _saved_selection(project)
    if target is None:
        _assert_no_resources(project)
        owner = str(uuid.uuid4())
        config = _fresh_config(project, owner, _free_ports())
        _assert_ports_available(config)
        target = {
            "database": DATABASE,
            "config": config,
            "lifecycle_version": 2,
            "owner": owner,
            "project": project,
            "selected_project": True,
            "status": "selected",
            "worktree": str(ROOT),
        }

    _archive_current_selection(current)
    _write_switch_journal(current, target)
    _write_marker(target)
    _write_compose_env(target["config"])
    SWITCH_JOURNAL.unlink()
    print(f"Selected Compose project {project} ({target['status']}).")


def recover_switch():
    _assert_local_engine()
    if not SWITCH_JOURNAL.exists():
        raise BootstrapError("There is no interrupted project switch to recover.")
    journal = _read_selection_file(SWITCH_JOURNAL)
    if set(journal) != {"from", "to"}:
        raise BootstrapError("The project switch journal is incomplete.")
    source, target = journal["from"], journal["to"]
    _verify_completed_selection(source, source.get("project"))
    if target.get("status") == "completed":
        _verify_completed_selection(target, target.get("project"))
    elif (
        target.get("status") == "selected"
        and target.get("worktree") == str(ROOT)
        and target.get("selected_project") is True
        and target.get("lifecycle_version") == 2
        and target.get("config", {}).get("COMPOSE_PROJECT_NAME")
        == target.get("project")
        and target.get("owner")
    ):
        _assert_no_resources(target["project"])
    else:
        raise BootstrapError("The switch target is not a verified selection.")
    active = _read_marker()
    persisted = _read_compose_env()
    source_env = all(
        persisted.get(key) == value for key, value in source["config"].items()
    )
    target_env = all(
        persisted.get(key) == value for key, value in target["config"].items()
    )
    if active == target and target_env:
        outcome = "completed"
    elif active == source and source_env:
        outcome = "unchanged"
    elif active == target and source_env:
        _write_marker(source)
        outcome = "rolled back"
    elif active == source and target_env:
        _write_compose_env(source["config"])
        outcome = "rolled back"
    else:
        raise BootstrapError(
            "The switch marker or Compose configuration changed unexpectedly; manual review is required."
        )
    SWITCH_JOURNAL.unlink()
    print(f"Interrupted project switch {outcome}; no resources were removed.")


def _assert_ports_available(config):
    keys = (
        "MEDILAB_ODOO_PORT",
        "MEDILAB_DB_PORT",
        "MEDILAB_GARAGE_PORT",
        "MEDILAB_GARAGE_ADMIN_PORT",
        "MEDILAB_CLOUDBEAVER_PORT",
    )
    seen = {}
    for key in keys:
        port = int(config[key])
        if port in seen:
            raise BootstrapError(
                f"{key} and {seen[port]} use the same host port {port}; configured ports must be distinct."
            )
        seen[port] = key
    for key in keys:
        port = int(config[key])
        host = "127.0.0.1" if key == "MEDILAB_GARAGE_ADMIN_PORT" else "0.0.0.0"
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind((host, port))
        except OSError as error:
            raise BootstrapError(
                f"Port {port} from {key} is unavailable; no bootstrap resources were changed. Set a free port in {COMPOSE_ENV_FILE} and retry only after checking the environment state."
            ) from error
        finally:
            probe.close()


def _create_owned_volumes(project, owner, config):
    for logical_name, key in (
        ("medilab-db", "MEDILAB_DB_VOLUME"),
        ("medilab-garage", "MEDILAB_GARAGE_VOLUME"),
        ("medilab-app", "MEDILAB_APP_VOLUME"),
        ("medilab-cloudbeaver", "MEDILAB_CLOUDBEAVER_VOLUME"),
    ):
        name = config[key]
        existing = _run(
            ["docker", "volume", "inspect", name],
            capture_output=True,
            check=False,
        )
        if existing.returncode == 0:
            raise BootstrapError(
                f"Volume {name!r} already exists; refusing to adopt it."
            )
        error_text = (existing.stderr or existing.stdout).lower()
        if not any(
            phrase in error_text
            for phrase in ("no such volume", "volume not found", "does not exist")
        ):
            raise BootstrapError(
                f"Could not verify that volume {name!r} is absent; refusing to create resources."
            )
        _run(
            [
                "docker",
                "volume",
                "create",
                "--label",
                f"{PROJECT_LABEL}={project}",
                "--label",
                f"{OWNER_LABEL}={owner}",
                "--label",
                f"com.docker.compose.volume={logical_name}",
                name,
            ]
        )


def _run(args, *, env=None, stdin=None, capture_output=False, check=True):
    return subprocess.run(
        args,
        cwd=ROOT,
        env=env,
        stdin=stdin,
        capture_output=capture_output,
        text=capture_output,
        check=check,
    )


def _run_odoo(args, *, env, stdin=None):
    command = [
        sys.executable,
        str(ODOO_LOG_PRESENTER),
        "--stdout-color",
        "auto",
        "--stderr-color",
        "auto",
        "--",
        *args,
    ]
    return _run(command, env=env, stdin=stdin)


def _run_oneoff_shell(project, owner, script, config):
    with script.open("rb") as source:
        _compose(
            project,
            True,
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "odoo",
            "odoo",
            "shell",
            ODOO_CONFIG_ARGUMENT,
            ODOO_NO_CRON_ARGUMENT,
            *ODOO_DATABASE_ARGUMENTS,
            "-d",
            DATABASE,
            stdin=source,
            owner=owner,
            owned=True,
            config=config,
            present_odoo_logs=True,
        )


def _prepare_accounting_foundation(project, owner, env):
    common = [ODOO_CONFIG_ARGUMENT, ODOO_NO_CRON_ARGUMENT, "-d", DATABASE]
    odoo_compose = _compose_args(project, owned=True, bootstrap=True)
    _run_odoo(
        [
            *odoo_compose,
            "run",
            "--rm",
            "--no-deps",
            "odoo",
            *common,
            "-i",
            "base",
            "--stop-after-init",
        ],
        env=env,
    )
    config = env
    _run_oneoff_shell(project, owner, SET_COUNTRY_SCRIPT, config)
    _run_odoo(
        [
            *odoo_compose,
            "run",
            "--rm",
            "--no-deps",
            "odoo",
            *common,
            "-i",
            "l10n_vn",
            "--stop-after-init",
        ],
        env=env,
    )
    _run_oneoff_shell(project, owner, ACCOUNTING_SCRIPT, config)


def _compose_environment(project, owner=None, config=None):
    allowed = {
        "ANSICON",
        "COLORTERM",
        "ConEmuANSI",
        "COMSPEC",
        "DOCKER_CONFIG",
        "DOCKER_CONTEXT",
        "DOCKER_HOST",
        "FORCE_COLOR",
        "HOME",
        "NO_COLOR",
        "PATH",
        "SYSTEMROOT",
        "TEMP",
        "TERM",
        "TMP",
        "USERPROFILE",
        "WINDIR",
        "WT_SESSION",
        "XDG_RUNTIME_DIR",
    }
    env = {key: value for key, value in os.environ.items() if key in allowed}
    env.update(
        {
            "COMPOSE_DISABLE_ENV_FILE": "1",
            "COMPOSE_PROJECT_NAME": project,
            "MEDILAB_DB_NAME": DATABASE,
            "MEDILAB_DB_PASSWORD": "root",
            "MEDILAB_DB_PORT": os.environ.get("MEDILAB_DB_PORT", "15432"),
            "MEDILAB_DB_USER": "root",
            "MEDILAB_DEMO_PASSWORD": "demo",
            "MEDILAB_GARAGE_ADMIN_PORT": os.environ.get(
                "MEDILAB_GARAGE_ADMIN_PORT", "3903"
            ),
            "MEDILAB_GARAGE_PORT": os.environ.get("MEDILAB_GARAGE_PORT", "3900"),
            "MEDILAB_ODOO_PORT": os.environ.get("MEDILAB_ODOO_PORT", "8069"),
            "BUCKET_LABORATORY_ACCESS_KEY": "GK000000000000000000000001",
            "BUCKET_LABORATORY_NAME": "laboratory-files",
            "BUCKET_LABORATORY_PUBLIC_ADDRESS": "http://localhost:3900",
            "BUCKET_LABORATORY_SECRET_KEY": "0" * 63 + "1",
            "CLOUDBEAVER_ADMIN_NAME": "medilab",
            "CLOUDBEAVER_ADMIN_PASSWORD": "admin",
            "GARAGE_ADMIN_TOKEN": "medilab-local-admin-token",
            "GARAGE_RPC_SECRET": "0" * 63 + "2",
            "MEDILAB_CLOUDBEAVER_PORT": os.environ.get(
                "MEDILAB_CLOUDBEAVER_PORT", "8978"
            ),
            "MEDILAB_ODOO_IMAGE": "medilab-odoo:local",
        }
    )
    if config:
        env.update(config)
        env["BUCKET_LABORATORY_PUBLIC_ADDRESS"] = (
            f"http://localhost:{env['MEDILAB_GARAGE_PORT']}"
        )
    if owner:
        env["MEDILAB_DEMO_BOOTSTRAP_OWNER"] = owner
    return env


def _compose(
    project,
    bootstrap,
    *args,
    owner=None,
    owned=False,
    config=None,
    stdin=None,
    capture_output=False,
    check=True,
    present_odoo_logs=False,
):
    command = _compose_args(project, owned=owned, bootstrap=bootstrap)
    command += list(args)
    env = _compose_environment(project, owner, config)
    if present_odoo_logs:
        command = [
            sys.executable,
            str(ODOO_LOG_PRESENTER),
            "--stdout-color",
            "auto",
            "--stderr-color",
            "auto",
            "--",
            *command,
        ]
    return _run(
        command, env=env, stdin=stdin, capture_output=capture_output, check=check
    )


def _compose_args(project, *, owned, bootstrap):
    command = ["docker", "compose", "-p", project, "-f", str(COMPOSE)]
    if owned:
        command += ["-f", str(OWNED_COMPOSE)]
    if bootstrap:
        command += ["-f", str(BOOTSTRAP_COMPOSE)]
    return command


def _inspect(kind, project):
    command = ["docker", kind]
    if kind == "ps":
        command.append("--all")
    else:
        command.append("ls")
    command += [
        "--quiet",
        "--filter",
        f"label={PROJECT_LABEL}={project}",
    ]
    result = _run(
        command,
        capture_output=True,
    )
    identities = result.stdout.split()
    if not identities:
        return []
    result = _run(["docker", "inspect", *identities], capture_output=True)
    return json.loads(result.stdout)


def _resources(project):
    return {
        "containers": _inspect("ps", project),
        "networks": _inspect("network", project),
        "volumes": _inspect("volume", project),
    }


def _named_resources(project):
    resources = {}
    for kind, command, prefix in (
        ("containers", ["docker", "ps", "--all"], f"{project}-"),
        ("networks", ["docker", "network", "ls"], f"{project}_"),
        ("volumes", ["docker", "volume", "ls"], f"{project}_"),
    ):
        result = _run(
            [
                *command,
                "--format",
                "{{.Names}}" if kind == "containers" else "{{.Name}}",
            ],
            capture_output=True,
        )
        resources[kind] = [
            name.lstrip("/")
            for name in result.stdout.splitlines()
            if name.lstrip("/").startswith(prefix)
        ]
    return resources


def _labels(resource, kind):
    if kind == "containers":
        return resource.get("Config", {}).get("Labels") or {}
    return resource.get("Labels") or resource.get("labels") or {}


def _assert_no_resources(project):
    resources = _resources(project)
    named = _named_resources(project)
    present = [
        f"{kind}={len(set(names) | {item.get('Name') or item.get('name') for item in resources[kind]})}"
        for kind, names in named.items()
        if names or resources[kind]
    ]
    if present:
        raise BootstrapError(
            f"Compose project {project!r} already owns resources ({', '.join(present)}); refusing to adopt or reset them."
        )


def _assert_owned_resources(project, owner):
    resources = _resources(project)
    named = _named_resources(project)
    for kind, items in resources.items():
        inspected_names = {
            (item.get("Name") or item.get("name") or "").lstrip("/") for item in items
        }
        if set(named[kind]) != inspected_names:
            raise BootstrapError(
                f"The names and Compose labels of {kind} do not identify the same owned resources; refusing to proceed."
            )
        for item in items:
            labels = _labels(item, kind)
            if labels.get(PROJECT_LABEL) != project or labels.get(OWNER_LABEL) != owner:
                raise BootstrapError(
                    f"Found a {kind[:-1]} without the expected bootstrap ownership labels; refusing cleanup."
                )
    return resources


def _owned_volume_names(project, owner):
    resources = _assert_owned_resources(project, owner)
    return tuple(
        sorted(item.get("Name") or item.get("name") for item in resources["volumes"])
    )


def _owned_volume_identities(project, owner):
    resources = _assert_owned_resources(project, owner)
    return tuple(
        sorted(
            (
                item.get("Name") or item.get("name"),
                item.get("Mountpoint") or item.get("mountpoint"),
                item.get("CreatedAt") or item.get("createdAt"),
                item.get("Driver") or item.get("driver"),
            )
            for item in resources["volumes"]
        )
    )


def _normal_app_ready(project, owner, config):
    _compose(
        project,
        False,
        "up",
        "-d",
        "--no-build",
        owner=owner,
        owned=True,
        config=config,
    )
    port = config["MEDILAB_ODOO_PORT"]
    url = f"http://127.0.0.1:{port}/web/login?db={DATABASE}"
    last_error = None
    for _attempt in range(120):
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
                last_error = f"HTTP {response.status}"
        except OSError as error:
            last_error = type(error).__name__
        time.sleep(2)
    raise BootstrapError(
        f"The normal Odoo application did not become ready at {url}: {last_error}."
    )


def _wait_for_service(
    project, bootstrap, service, *health_command, owner=None, config=None
):
    last_error = "no response"
    for _attempt in range(60):
        result = _compose(
            project,
            bootstrap,
            "exec",
            "-T",
            service,
            *health_command,
            owner=owner,
            owned=bool(config),
            config=config,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return
        last_error = (result.stderr or result.stdout).strip().splitlines()
        last_error = (
            last_error[-1] if last_error else f"exit status {result.returncode}"
        )
        time.sleep(2)
    raise BootstrapError(
        f"The private {service} service did not become ready: {last_error}."
    )


def _shell(project, owner, script, *, bootstrap, config):
    command = ["exec", "-T"]
    if not bootstrap:
        command += ["--env", f"MEDILAB_DEMO_BOOTSTRAP_OWNER={owner}"]
    command += [
        "odoo",
        "odoo",
        "shell",
        ODOO_CONFIG_ARGUMENT,
        ODOO_NO_CRON_ARGUMENT,
        *ODOO_DATABASE_ARGUMENTS,
        "-d",
        DATABASE,
    ]
    with script.open("rb") as source:
        _compose(
            project,
            bootstrap,
            *command,
            stdin=source,
            owner=owner,
            owned=True,
            config=config,
            present_odoo_logs=True,
        )


def _read_database_state(project, owner, config):
    script = ROOT / "tools/scripts/demo_bootstrap_state.py"
    with script.open("rb") as source:
        result = _compose(
            project,
            False,
            "exec",
            "-T",
            "odoo",
            "odoo",
            "shell",
            ODOO_CONFIG_ARGUMENT,
            ODOO_NO_CRON_ARGUMENT,
            *ODOO_DATABASE_ARGUMENTS,
            "-d",
            DATABASE,
            stdin=source,
            capture_output=True,
            owner=owner,
            owned=True,
            config=config,
            present_odoo_logs=True,
        )
    for line in reversed(result.stdout.splitlines()):
        try:
            state = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(state, dict) and "status" in state:
            if state.get("owner") != owner:
                raise BootstrapError(
                    "The database bootstrap owner does not match the local resource marker."
                )
            return state
    raise BootstrapError(
        "Could not read a valid bootstrap state from the isolated database."
    )


def _handoff(project, owner, marker):
    config = marker["config"]
    if marker["status"] == "seeded":
        _compose(
            project,
            True,
            "stop",
            "odoo",
            owner=owner,
            owned=True,
            config=config,
        )
        marker["status"] = "handoff"
        _write_marker(marker)
    volumes_before = _owned_volume_identities(project, owner)
    _normal_app_ready(project, owner, config)
    if _owned_volume_identities(project, owner) != volumes_before:
        raise BootstrapError("Persistent volume identities changed during handoff.")
    if marker["status"] != "completed":
        _shell(
            project,
            owner,
            ROOT / "tools/scripts/demo_bootstrap_complete.py",
            bootstrap=False,
            config=config,
        )
        marker["status"] = "completed"
        marker.pop("disposable", None)
        marker["lifecycle_version"] = 2
        marker["handoff_verified"] = True
        _write_marker(marker)


def _validate_setup_marker(project, marker):
    if not marker:
        return
    if marker.get("project") != project:
        raise BootstrapError(
            "The local bootstrap marker belongs to a different Compose project."
        )
    if marker.get("lifecycle_version") != 2:
        raise BootstrapError(
            "This bootstrap was created by an older lifecycle and will not be adopted or resumed automatically. Its resources are preserved."
        )
    status = marker.get("status")
    if status in ("creating", "installing", "running", "failed"):
        raise BootstrapError(
            f"A bootstrap attempt is {status}; do not retry it. Verify ownership and run `task setup:fresh:recover` first."
        )
    if status not in ("seeded", "handoff", "completed", "selected", "discarded"):
        raise BootstrapError(
            "The local bootstrap marker has an unknown state; refusing to adopt its resources."
        )


def _resume_setup(project, marker):
    owner = marker["owner"]
    config = marker["config"]
    _assert_owned_resources(project, owner)
    actual_volumes = set(_owned_volume_names(project, owner))
    expected_volumes = {
        config[key]
        for key in (
            "MEDILAB_DB_VOLUME",
            "MEDILAB_GARAGE_VOLUME",
            "MEDILAB_APP_VOLUME",
            "MEDILAB_CLOUDBEAVER_VOLUME",
        )
    }
    if actual_volumes != expected_volumes:
        raise BootstrapError(
            "The bootstrap volume identities differ from the saved environment configuration; refusing handoff."
        )
    if marker.get("status") == "seeded":
        _compose(
            project,
            True,
            "stop",
            "odoo",
            owner=owner,
            owned=True,
            config=config,
        )
        marker["status"] = "handoff"
        _write_marker(marker)
    if marker.get("status") == "completed":
        _normal_app_ready(project, owner, config)
        state = _read_database_state(project, owner, config)
        if state.get("status") != "completed":
            raise BootstrapError(
                f"Database bootstrap state is {state.get('status')!r}; refusing normal startup."
            )
        return
    _handoff(project, owner, marker)


def setup():
    _assert_local_engine()
    project = project_name()
    marker = _read_marker()
    _validate_setup_marker(project, marker)
    if marker and marker.get("status") in ("seeded", "handoff", "completed"):
        _resume_setup(project, marker)
        return

    _assert_no_resources(project)
    owner = (
        marker["owner"]
        if marker and marker["status"] == "selected"
        else str(uuid.uuid4())
    )
    config = (
        marker["config"]
        if marker and marker["status"] == "selected"
        else _fresh_config(project, owner)
    )
    _assert_ports_available(config)
    marker = {
        **(marker or {}),
        "database": DATABASE,
        "config": config,
        "disposable": True,
        "lifecycle_version": 2,
        "owner": owner,
        "project": project,
        "status": "creating",
    }
    _write_marker(marker)
    _write_compose_env(config)
    env = _compose_environment(project, owner, config)
    try:
        _create_owned_volumes(project, owner, config)
        bootstrap_args = _compose_args(project, owned=True, bootstrap=True)
        _run([*bootstrap_args, "build", "odoo"], env=env)
        _run(
            [*bootstrap_args, "up", "-d", "postgres", "garage"],
            env=env,
        )
        _wait_for_service(
            project,
            True,
            "postgres",
            "pg_isready",
            "-U",
            "root",
            "-d",
            DATABASE,
            owner=owner,
            config=config,
        )
        _wait_for_service(
            project,
            True,
            "garage",
            "/garage",
            "health",
            owner=owner,
            config=config,
        )
        _compose(
            project,
            True,
            "run",
            "--rm",
            "--no-deps",
            "garage-setup",
            owner=owner,
            owned=True,
            config=config,
        )
        marker["status"] = "installing"
        _write_marker(marker)
        _prepare_accounting_foundation(project, owner, env)
        modules = ",".join(MODULES)
        _run_odoo(
            [
                *bootstrap_args,
                "run",
                "--rm",
                "--no-deps",
                "odoo",
                ODOO_CONFIG_ARGUMENT,
                ODOO_NO_CRON_ARGUMENT,
                "-d",
                DATABASE,
                "-i",
                modules,
                "--stop-after-init",
            ],
            env=env,
        )
        marker["status"] = "running"
        _write_marker(marker)
        _compose(
            project,
            True,
            "up",
            "-d",
            "odoo",
            owner=owner,
            owned=True,
            config=config,
        )
        _compose(
            project,
            True,
            "exec",
            "-T",
            "odoo",
            "python3",
            "/opt/medilab/scripts/demo_bootstrap_probe.py",
            "--database",
            DATABASE,
            owner=owner,
            owned=True,
            config=config,
            present_odoo_logs=True,
        )
        _shell(
            project,
            owner,
            ROOT / "tools/scripts/demo_bootstrap_runner.py",
            bootstrap=True,
            config=config,
        )
        marker["status"] = "seeded"
        _write_marker(marker)
        _handoff(project, owner, marker)
    except BaseException:
        if marker.get("status") not in ("seeded", "handoff", "completed"):
            marker["status"] = "failed"
            _write_marker(marker)
        _compose(
            project,
            True,
            "stop",
            "odoo",
            owner=owner,
            owned=True,
            config=config,
            check=False,
        )
        raise


def check_normal_setup():
    marker = _read_marker()
    if not marker:
        resources = _resources(project_name())
        if any(
            _labels(resource, kind).get(OWNER_LABEL)
            for kind, items in resources.items()
            for resource in items
        ):
            raise BootstrapError(
                "Bootstrap-owned resources exist but their local ownership marker is missing; refusing normal setup."
            )
        return
    if marker.get("project") != project_name():
        raise BootstrapError(
            "The local bootstrap marker belongs to a different Compose project."
        )
    if marker.get("status") not in ("completed", "discarded"):
        raise BootstrapError(
            f"Fresh demo bootstrap is {marker.get('status')!r}; run `task setup:fresh` to resume handoff or `task setup:fresh:recover` to discard its owned resources before normal setup."
        )
    if marker.get("status") == "discarded":
        _assert_no_resources(marker["project"])
    elif (
        marker.get("lifecycle_version") != 2
        or marker.get("handoff_verified") is not True
    ):
        raise BootstrapError(
            "The bootstrap handoff is not verified; ordinary setup is blocked. Resume with `task setup:fresh`."
        )


def recover():
    _assert_local_engine()
    marker = _read_marker()
    if not marker or marker.get("status") not in (
        "creating",
        "installing",
        "running",
        "failed",
    ):
        raise BootstrapError(
            "There is no failed or interrupted fresh bootstrap to recover."
        )
    if marker.get("lifecycle_version") != 2:
        raise BootstrapError(
            "This failed attempt uses an older ownership model; automatic cleanup is refused and its resources are preserved."
        )
    project = marker.get("project")
    if project != project_name():
        raise BootstrapError(
            "The failed bootstrap belongs to a different worktree project."
        )
    resources = _assert_owned_resources(project, marker["owner"])
    summary = {
        kind: [
            item.get("Name") or item.get("name") or item.get("Id") or item.get("id")
            for item in items
        ]
        for kind, items in resources.items()
    }
    print(
        json.dumps(
            {"project": project, "owner": marker["owner"], "resources": summary},
            indent=2,
        )
    )
    confirmation = input(
        f"Type {marker['owner']} to stop and remove only these isolated bootstrap resources: "
    )
    if confirmation != marker["owner"]:
        raise BootstrapError("Recovery was not confirmed; no resources were removed.")
    for container in resources["containers"]:
        _run(["docker", "stop", container["Id"]], check=False)
        _run(["docker", "rm", container["Id"]], check=False)
    for volume in resources["volumes"]:
        _run(["docker", "volume", "rm", volume["Name"]])
    for network in resources["networks"]:
        _run(
            ["docker", "network", "rm", network.get("Id") or network["id"]],
            check=False,
        )
    marker["status"] = "discarded"
    marker.pop("disposable", None)
    _write_marker(marker)


def reset():
    _assert_local_engine()
    marker = _read_marker()
    if (
        not marker
        or marker.get("status") != "completed"
        or marker.get("lifecycle_version") != 2
        or marker.get("handoff_verified") is not True
    ):
        raise BootstrapError(
            "Reset refused: there is no verified fresh bootstrap owned by this worktree. Existing or ambiguous environments are never deleted."
        )
    project = marker.get("project")
    if project != project_name():
        raise BootstrapError(
            "Reset refused: the completed bootstrap belongs to a different Compose project."
        )
    resources = _assert_owned_resources(project, marker["owner"])
    expected_volumes = {
        marker["config"][key]
        for key in (
            "MEDILAB_DB_VOLUME",
            "MEDILAB_GARAGE_VOLUME",
            "MEDILAB_APP_VOLUME",
            "MEDILAB_CLOUDBEAVER_VOLUME",
        )
    }
    if set(_owned_volume_names(project, marker["owner"])) != expected_volumes:
        raise BootstrapError(
            "Reset refused: owned persistent volume identities do not match the completed bootstrap marker."
        )
    summary = {
        kind: [
            item.get("Name") or item.get("name") or item.get("Id") or item.get("id")
            for item in items
        ]
        for kind, items in resources.items()
    }
    print(json.dumps({"project": project, "resources": summary}, indent=2))
    confirmation = input(
        f"Type {marker['owner']} to delete only this verified local demo environment and recreate it: "
    )
    if confirmation != marker["owner"]:
        raise BootstrapError("Reset was not confirmed; no resources were removed.")
    for container in resources["containers"]:
        _run(["docker", "stop", container["Id"]], check=False)
        _run(["docker", "rm", container["Id"]], check=False)
    for network in resources["networks"]:
        _run(
            ["docker", "network", "rm", network.get("Id") or network["id"]],
            check=False,
        )
    for volume in resources["volumes"]:
        _run(["docker", "volume", "rm", volume["Name"]])
    marker["status"] = "discarded"
    _write_marker(marker)


def main():
    commands = {
        "select": select,
        "switch": switch,
        "switch-recover": recover_switch,
        "setup": setup,
        "recover": recover,
        "check-normal": check_normal_setup,
        "reset": reset,
    }
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        raise SystemExit(
            "Usage: python tools/scripts/demo_bootstrap.py select|switch|switch-recover|setup|recover|check-normal|reset"
        )
    action = sys.argv[1]
    try:
        if len(sys.argv) != 2:
            message = (
                "Use `task setup:fresh:select PROJECT=medilab-bootstrap-test-01`."
                if action in ("select", "switch")
                else "This command takes no arguments."
            )
            raise BootstrapError(message)
        if action in ("select", "switch"):
            commands[action](os.environ.get("MEDILAB_SELECTED_PROJECT", ""))
        else:
            commands[action]()
    except (
        BootstrapError,
        ValueError,
        subprocess.CalledProcessError,
        OSError,
    ) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(getattr(error, "returncode", 1) or 1) from error


if __name__ == "__main__":
    main()
