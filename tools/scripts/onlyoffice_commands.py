"""Owned ONLYOFFICE command dispatch."""

import json
import os
import subprocess
import sys
from pathlib import Path

import demo_bootstrap as bootstrap
import onlyoffice_setup
from onlyoffice_state import OnlyofficeError


def use_core_environment(controller, command):
    if command in {"setup", "up", "restart", "verify", "config-check"}:
        _run_in_core_environment(controller, command)


def _run_in_core_environment(controller, command):
    virtual = controller.ROOT / "src/core/.venv"
    if Path(sys.prefix).resolve() != virtual.resolve():
        executable = virtual / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        if not executable.is_file():
            raise OnlyofficeError(
                "The locked core Python environment is missing. Run task onlyoffice:setup after installing uv and Python 3.12 or later."
            )
        raise SystemExit(
            subprocess.run(
                [str(executable), str(Path(controller.__file__).resolve()), command],
                cwd=controller.ROOT,
                check=False,
            ).returncode
        )


def _maintenance_command(controller, command, project, state, marker, environment):
    if command == "guard-existing":
        controller.guard_existing(project, state, environment)
        return True
    if command == "recover-registration":
        if state:
            with controller.locked(
                controller.state_directory(project, state.get("base_owner"))
            ):
                controller.recover_registration(state, marker)
        return True
    return False


def _report_status(controller, state):
    status = controller.actual_status(state)
    print(json.dumps(status))
    if not status["ready"]:
        raise SystemExit(1)


def _print_logs(controller, state):
    for peer in controller.owned_containers(state):
        result = controller.run(["docker", "logs", "--tail", "100", peer["Id"]])
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)


def _start_completed(controller, command, project, state, marker, environment):
    if state["status"] != "completed":
        raise OnlyofficeError(
            "ONLYOFFICE preparation is incomplete; resume onlyoffice:setup."
        )
    if command == "restart":
        controller.stop(state, marker, environment)
    controller.create_resources(state)
    controller.handoff_public_port(state, marker, environment)
    onlyoffice_setup.start_editor(controller, state, marker, environment)
    controller.guard_existing(project, state, environment)
    controller.compose(state, marker, environment, "up", "-d", "--no-deps", "odoo")


def _locked_command(controller, command, project, state, marker, environment):
    with controller.locked(
        controller.state_directory(project, state.get("base_owner"))
    ):
        if command == "down":
            controller.stop(state, marker, environment)
            controller.remove_owned_containers(state)
        elif command in {"up", "restart"}:
            _start_completed(controller, command, project, state, marker, environment)
        elif command == "verify":
            controller.verify_network(state, marker, environment)
            controller.verify_runtime(state, marker, environment)
            print(
                "ONLYOFFICE actual conversion, callback refusal and network verification passed."
            )


def execute(controller, command):
    project, marker, engine, environment = controller.selection(
        secure_engine=command in {"up", "restart", "verify", "config-check"},
        recovering=command in {"recover-registration", "guard-existing"},
        validate_inputs=command
        in {"guard-existing", "up", "restart", "verify", "config-check"},
    )
    state = controller.read_state(project, marker, engine)
    if _maintenance_command(controller, command, project, state, marker, environment):
        return
    if not state:
        raise OnlyofficeError(
            "ONLYOFFICE has not been prepared for this selection; run task onlyoffice:setup."
        )
    if state["status"] == "completed":
        controller.verify_registration(state, marker, bootstrap._read_compose_env())
    if command == "status":
        _report_status(controller, state)
        return
    controller.resources(
        state,
        preparing=command in {"logs", "down"},
        inspect_policy=command not in {"logs", "down"},
    )
    if command == "logs":
        _print_logs(controller, state)
        return
    if command in {"up", "restart", "verify", "config-check"}:
        controller.guard_existing(project, state, environment)
        onlyoffice_setup.verify_configuration(
            controller,
            controller.state_directory(project, state.get("base_owner")),
            state,
            environment,
        )
    if command == "config-check":
        controller.compose(state, marker, environment, "config", "--quiet")
        controller.verify_identity(state, marker, environment)
        print("ONLYOFFICE configuration and ownership are valid.")
        return
    _locked_command(controller, command, project, state, marker, environment)
