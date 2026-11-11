"""Owned ONLYOFFICE setup and material preparation."""

import json
import os
import tempfile
from pathlib import Path

import demo_bootstrap as bootstrap
from local_private_paths import LocalPrivatePathError, ensure_local_directory
from onlyoffice_state import OnlyofficeError, material_fingerprints


def _prepare_directory(controller, directory, directory_root):
    controller.checked_path(directory_root)
    if (
        directory.exists()
        and not (directory / "state.json").exists()
        and any(item.name != "operation.lock" for item in directory.iterdir())
    ):
        raise OnlyofficeError(
            "ONLYOFFICE private files exist without their ownership marker; refusing adoption."
        )
    if directory.exists():
        controller.checked_path(directory, private=True)
    else:
        try:
            ensure_local_directory(controller.ROOT, directory)
        except LocalPrivatePathError as error:
            raise OnlyofficeError(str(error)) from None


def _initial_state(controller, state, project, marker, engine):
    if not state:
        for kind, items in bootstrap._resources(project).items():
            for resource in items:
                if controller.addon_resource(resource, kind, project):
                    raise OnlyofficeError(
                        "Unowned ONLYOFFICE resources already exist in this project; no resources were adopted."
                    )
        state = controller.new_state(project, marker, engine)
        controller.save(state)
    return state


def _prepare_jwt(controller, directory, state, environment, generate_secret):
    jwt = controller.checked_path(directory / "jwt", private=True)
    if not jwt.exists():
        if state.get("material"):
            raise OnlyofficeError(
                "Prepared ONLYOFFICE secret material is missing; it will not be regenerated."
            )
        descriptor, temporary = tempfile.mkstemp(prefix=".jwt-", dir=directory)
        try:
            with os.fdopen(descriptor, "w", encoding="ascii") as output:
                output.write(
                    environment.get("ONLYOFFICE_JWT_SECRET") or generate_secret(48)
                )
                output.flush()
                os.fsync(output.fileno())
            controller.protect(Path(temporary))
            os.link(temporary, jwt)
        finally:
            Path(temporary).unlink(missing_ok=True)


def _prepare_state(
    controller, state, project, marker, engine, environment, directory, generate_secret
):
    state = _initial_state(controller, state, project, marker, engine)
    controller.registration(state, marker)
    if marker:
        environment = bootstrap._compose_environment(
            project, marker["owner"], marker["config"]
        )
    from onlyoffice_tls import prepare

    prepare(directory, project, state["owner"])
    _prepare_jwt(controller, directory, state, environment, generate_secret)
    expected = controller.runtime_config(state, environment)
    config_file = directory / controller.RUNTIME_FILE
    if config_file.exists():
        if json.loads(config_file.read_text()) != expected:
            raise OnlyofficeError(
                "The prepared ONLYOFFICE endpoint configuration changed; existing identities were preserved."
            )
    else:
        controller.atomic_json(config_file, expected)
    material = material_fingerprints(directory)
    if state.get("material") and state["material"] != material:
        raise OnlyofficeError(
            "Prepared ONLYOFFICE secret material changed outside its ownership state."
        )
    state["material"] = material
    controller.save(state)
    return (state, environment)


def verify_configuration(controller, directory, state, environment):
    from onlyoffice_tls import verify

    verify(directory)
    if json.loads(
        (directory / controller.RUNTIME_FILE).read_text(encoding="utf-8")
    ) != controller.runtime_config(state, environment):
        raise OnlyofficeError(
            "The selected local endpoint configuration differs from the owned editor configuration."
        )


def start_editor(controller, state, marker, environment):
    try:
        controller.compose(
            state, marker, environment, "up", "-d", "--wait", *controller.SERVICES
        )
        controller.verify_network(state, marker, environment)
    except Exception:
        controller.stop(state, marker, environment)
        raise


def setup(controller, directory_root, generate_secret):
    project, marker, engine, environment = controller.selection(
        recovering=True, validate_inputs=True, secure_engine=True
    )
    controller.guard_existing(
        project, controller.read_state(project, marker, engine), environment
    )
    directory = controller.state_directory(project, (marker or {}).get("owner"))
    _prepare_directory(controller, directory, directory_root)
    with controller.locked(directory):
        state = controller.read_state(project, marker, engine)
        if state and state["status"] == "completed":
            controller.resources(state)
            controller.recover_registration(state, marker)
            controller.verify_registration(state, marker, bootstrap._read_compose_env())
        else:
            state, environment = _prepare_state(
                controller,
                state,
                project,
                marker,
                engine,
                environment,
                directory,
                generate_secret,
            )
        verify_configuration(controller, directory, state, environment)
        controller.create_resources(state, allow_volumes=state["status"] != "completed")
        controller.compose(state, marker, environment, "config", "--quiet")
        controller.handoff_public_port(state, marker, environment)
        start_editor(controller, state, marker, environment)
        controller.guard_existing(project, state, environment)
        controller.compose(state, marker, environment, "up", "-d", "--no-deps", "odoo")
        controller.verify_runtime(state, marker, environment)
        state["status"] = "completed"
        controller.save(state)
    print(
        f"ONLYOFFICE setup and integration verification completed: http://localhost:{state['config']['MEDILAB_ONLYOFFICE_PORT']}."
    )
