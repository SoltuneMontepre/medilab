"""Run local app Compose commands against this checkout's verified environment.

Usage: python tools/scripts/local_compose.py <Compose arguments> or guard-demo-install <modules>
Completed fresh bootstrap environments use their persisted, owner-checked Compose and volume configuration.
"""

import contextlib
import os
import subprocess
import sys

from compose_env import project_name
from demo_bootstrap import (
    BOOTSTRAP_COMPOSE,
    COMPOSE,
    OWNED_COMPOSE,
    BootstrapError,
    _assert_owned_resources,
    _compose_environment,
    _labels,
    _owned_volume_names,
    _read_compose_env,
    _read_marker,
    _resources,
    _volume_mismatch,
    _volume_mismatch_message,
)
from onlyoffice_state import OnlyofficeError, missing_core_volumes, resolve_addon

COMPOSE_COMMANDS = {"up", "down", "stop", "restart", "logs", "ps", "run", "exec"}
COMPOSE_IDENTITY_OPTIONS = {
    "-p",
    "--project-name",
    "-f",
    "--file",
    "--env-file",
    "--project-directory",
}


def _checked_arguments(arguments):
    if arguments[0] not in COMPOSE_COMMANDS:
        raise BootstrapError(
            f"Compose command {arguments[0]!r} is not supported by the local environment wrapper."
        )
    if arguments[0] == "down" and len(arguments) != 1:
        raise BootstrapError(
            "Compose down options are refused; use guarded `task reset` for disposable resources."
        )
    if any(
        argument in COMPOSE_IDENTITY_OPTIONS
        or (len(argument) > 2 and argument.startswith(("-p", "-f")))
        or any(
            argument.startswith(option + "=")
            for option in COMPOSE_IDENTITY_OPTIONS
            if option.startswith("--")
        )
        for argument in arguments[1:]
    ):
        raise BootstrapError(
            "Compose project and file overrides are refused by the local environment wrapper."
        )
    return arguments


def _completed_configuration(project, marker):
    config = marker.get("config") or {}
    owner = marker.get("owner")
    persisted = _read_compose_env()
    missing = [key for key, value in config.items() if persisted.get(key) != value]
    if missing:
        raise BootstrapError(
            f"Saved Compose configuration differs for {', '.join(missing)}; refusing to start or recreate services."
        )
    _assert_owned_resources(project, owner)
    missing_volumes, unexpected_volumes = _volume_mismatch(
        config, _owned_volume_names(project, owner)
    )
    if missing_core_volumes(config, missing_volumes) or unexpected_volumes:
        raise BootstrapError(
            _volume_mismatch_message(missing_volumes, unexpected_volumes)
        )
    files = ["-f", str(COMPOSE), "-f", str(OWNED_COMPOSE)]
    environment = _compose_environment(project, owner, config)
    if dev_mode := os.environ.get("ODOO_DEV"):
        environment["ODOO_DEV"] = dev_mode
    return project, marker, files, environment


def _resolve(command):
    project = project_name()
    marker = _read_marker()
    if not marker:
        resources = _resources(project)
        if any(
            _labels(resource, kind).get("com.medilab.bootstrap.owner")
            for kind, items in resources.items()
            for resource in items
        ):
            raise BootstrapError(
                "This project has bootstrap-owned resources but no matching local marker; refusing Compose operations."
            )
        return project, None, ["-f", str(COMPOSE)], os.environ.copy()

    if marker.get("project") != project:
        raise BootstrapError(
            "The bootstrap marker belongs to a different checkout; refusing Compose operations."
        )
    if marker.get("lifecycle_version") != 2:
        raise BootstrapError(
            "This environment uses an older bootstrap lifecycle; refusing Compose operations until it is explicitly reviewed."
        )
    status = marker.get("status")
    config = marker.get("config") or {}
    owner = marker.get("owner")
    if status == "completed":
        return _completed_configuration(project, marker)

    if status in ("creating", "installing", "running", "seeded", "handoff", "failed"):
        if command not in ("stop", "down", "logs", "ps"):
            raise BootstrapError(
                f"Fresh bootstrap is {status!r}; normal Compose operations are blocked. Resume with `task setup:fresh` or inspect with `task setup:fresh:recover`."
            )
        _assert_owned_resources(project, owner)
        files = [
            "-f",
            str(COMPOSE),
            "-f",
            str(OWNED_COMPOSE),
            "-f",
            str(BOOTSTRAP_COMPOSE),
        ]
        return project, marker, files, _compose_environment(project, owner, config)

    raise BootstrapError(
        f"Bootstrap state is {status!r}; refusing to start services from a discarded or unknown environment."
    )


def guard_demo_install(modules):
    requested = {module.strip() for module in modules.replace(" ", ",").split(",")}
    if "sol_demo" not in requested:
        return
    project, _marker, files, env = _resolve("guard-demo-install")
    db_user = env.get(
        "MEDILAB_DB_USER", _read_compose_env().get("MEDILAB_DB_USER", "root")
    )
    query = [
        "docker",
        "compose",
        "-p",
        project,
        *files,
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        db_user,
        "-d",
        "medilab",
        "-Atqc",
        "SELECT state FROM ir_module_module WHERE name = 'sol_demo'",
    ]
    result = subprocess.run(query, env=env, capture_output=True, text=True, check=False)
    if result.returncode or result.stdout.strip() != "installed":
        raise BootstrapError(
            "Refusing to install sol_demo through `task upgrade`: its post-init hook renders PDFs and requires the fresh private HTTP bootstrap. Use `task setup:fresh` only for an empty isolated environment."
        )


def guard_e2e_app():
    _project, marker, _files, _environment = _resolve("guard-e2e-app")
    if marker:
        raise BootstrapError(
            "Browser-test module installation cannot modify a fresh demo database; use a separate disposable test environment."
        )


def guard_uninstall():
    _project, marker, _files, _environment = _resolve("guard-uninstall")
    if marker:
        raise BootstrapError(
            "Uninstall tests cannot write to a fresh demo filestore; use an unowned disposable test environment."
        )


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__.splitlines()[-1])
    try:
        if sys.argv[1] == "guard-demo-install":
            if len(sys.argv) != 3:
                raise SystemExit("Usage: local_compose.py guard-demo-install <modules>")
            guard_demo_install(sys.argv[2])
            return
        if sys.argv[1] == "guard-e2e-app":
            if len(sys.argv) != 2:
                raise SystemExit("Usage: local_compose.py guard-e2e-app")
            guard_e2e_app()
            return
        if sys.argv[1] == "guard-uninstall":
            if len(sys.argv) != 2:
                raise SystemExit("Usage: local_compose.py guard-uninstall")
            guard_uninstall()
            return
        arguments = _checked_arguments(sys.argv[1:])
        project, _marker, files, env = _resolve(arguments[0])
        extra_files, extra_env = resolve_addon(project, _marker, env, arguments[0])
        files += extra_files
        env.update(extra_env)
        command = ["docker", "compose", "-p", project, *files, *arguments]
        drain = contextlib.nullcontext()
        if arguments[0] == "down" and extra_files:
            from onlyoffice import drained_for_compose

            drain = drained_for_compose(project, _marker, env)
        with drain:
            result = subprocess.run(command, env=env, check=False)
        raise SystemExit(result.returncode)
    except (BootstrapError, OnlyofficeError, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
