"""Manage ONLYOFFICE in the selected local Compose project without adopting or deleting user data.

Usage: python tools/scripts/onlyoffice.py setup|guard-existing|recover-registration|up|down|restart|status|logs|verify|config-check
"""

import contextlib
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import demo_bootstrap as bootstrap
import onlyoffice_checks
import onlyoffice_lifecycle
from compose_env import project_name
from onlyoffice_state import (
    CONFIG_KEYS,
    DIRECTORY,
    INPUT_KEYS,
    OVERLAY,
    OWNER_LABEL,
    ROOT,
    SERVER_OVERLAY,
    SERVICES,
    VOLUME_KEYS,
    OnlyofficeError,
    assert_configuration_matches,
    assert_network_policy,
    atomic_json,
    checked_path,
    configuration_inputs,
    expected_configuration,
    material_fingerprints,
    network_driver_options,
    optional_volume_names,
    protect,
    read_state,
    runtime_environment,
    state_directory,
    verify_registration,
)


def run(arguments, *, environment=None, data=None, timeout=180, check=True):
    try:
        result = subprocess.run(
            arguments,
            cwd=ROOT,
            env=environment,
            input=data,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise OnlyofficeError(
            "The local container operation did not complete; inspect onlyoffice:status and retry owned setup."
        ) from None
    if check and result.returncode:
        raise OnlyofficeError(
            "The local container operation failed; inspect onlyoffice:status and the redacted onlyoffice:logs."
        )
    return result


def selection(*, recovering=False, validate_inputs=False, secure_engine=False):
    project = project_name()
    engine = bootstrap._assert_local_engine()
    if secure_engine:
        from host_tools import HostError, assert_onlyoffice_engine

        try:
            assert_onlyoffice_engine(
                json.loads(run(["docker", "info", "--format", "{{json .}}"]).stdout)
            )
        except HostError as error:
            raise OnlyofficeError(str(error)) from None
    marker = bootstrap._read_marker()
    if marker:
        bootstrap._validate_completed_selection(marker, project)
        bootstrap._assert_owned_resources(project, marker["owner"])
        if marker.get("engine") and marker["engine"] != engine:
            raise OnlyofficeError(
                "The selected engine differs from the completed local environment."
            )
    if not recovering:
        from local_compose import _resolve

        _resolve("ps")
    environment = (
        bootstrap._compose_environment(project, marker.get("owner"), marker["config"])
        if marker
        else dict(os.environ)
    )
    provided = (
        configuration_inputs(environment, fresh=bool(marker)) if validate_inputs else {}
    )
    if not marker:
        environment.update(
            {
                key: value
                for key, value in bootstrap._read_compose_env().items()
                if not key.startswith(("DOCKER_", "CONTAINER_"))
            }
        )
    environment.update(provided)
    return project, marker, engine, environment


def addon_resource(resource, kind, project):
    service = bootstrap._labels(resource, kind).get("com.docker.compose.service")
    name = (resource.get("Name") or resource.get("name") or "").lstrip("/")
    return service in SERVICES or name.startswith(
        (project + "_onlyoffice", project + "-onlyoffice-")
    )


def guard_existing(project, state, environment):
    provided = configuration_inputs(environment, fresh=True)
    if not state and any(key != "ONLYOFFICE_JWT_SECRET" for key in provided):
        raise OnlyofficeError(
            "Explicit editing-service origins, certificate paths or ports already configure this environment. Preserve that configuration and use its maintenance workflow or a separate isolated demo; automatic migration is refused."
        )
    expected = expected_configuration(state) if state else {}
    if state:
        checked = dict(provided)
        if "ONLYOFFICE_JWT_SECRET" not in expected and not state.get("material"):
            checked.pop("ONLYOFFICE_JWT_SECRET", None)
        assert_configuration_matches(checked, expected)
    inventory = bootstrap._resources(project)
    for kind, items in inventory.items():
        for resource in items:
            if addon_resource(resource, kind, project):
                if not state:
                    raise OnlyofficeError(
                        "Unmanaged ONLYOFFICE resources already exist. Preserve them and use their existing maintenance workflow or a separate isolated demo."
                    )
                assert_resource(resource, state, kind)
            if (
                kind != "containers"
                or bootstrap._labels(resource, kind).get("com.docker.compose.service")
                != "odoo"
            ):
                continue
            values = {}
            for entry in resource.get("Config", {}).get("Env") or []:
                key, separator, value = entry.partition("=")
                if separator and key in INPUT_KEYS and value:
                    values[key] = value
            if values and not state:
                raise OnlyofficeError(
                    "Odoo already has unmanaged editing-service configuration. Preserve it and use its existing maintenance workflow or a separate isolated demo; automatic migration is refused."
                )
            if state:
                assert_configuration_matches(values, expected)


@contextlib.contextmanager
def locked(directory):
    file = checked_path(directory / "operation.lock")
    stream = file.open("a+b")
    protect(file)
    try:
        if os.name == "nt":
            import msvcrt

            if file.stat().st_size == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        stream.close()
        raise OnlyofficeError(
            "Another ONLYOFFICE operation owns this selection; wait for it to finish."
        ) from None
    try:
        yield
    finally:
        stream.close()


def save(state):
    atomic_json(
        state_directory(state["project"], state.get("base_owner")) / "state.json", state
    )


def port_available(port):
    with socket.socket() as listener:
        try:
            listener.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def new_state(project, marker, engine):
    owner = uuid.uuid4().hex
    used = set(bootstrap._published_ports())
    configured = bootstrap._read_compose_env()
    used.update(
        int(configured[key])
        for key in bootstrap.PORT_KEYS
        if configured.get(key, "").isdigit()
    )
    port = next(
        (
            candidate
            for candidate in [29843, *range(30000, 32768)]
            if candidate not in used and port_available(candidate)
        ),
        None,
    )
    if not port:
        raise OnlyofficeError(
            "No unused local ONLYOFFICE port below 32768 is available."
        )
    config = {
        key: f"{project}_onlyoffice_{kind}_{owner[:12]}"
        for key, kind in zip(VOLUME_KEYS, ("lib", "data", "fonts"), strict=True)
    }
    config["MEDILAB_ONLYOFFICE_PORT"] = str(port)
    return {
        "format": 1,
        "project": project,
        "worktree": str(ROOT),
        "base_owner": (marker or {}).get("owner"),
        "engine": engine,
        "owner": owner,
        "config": config,
        "http_port": 18081
        if configured.get("MEDILAB_GARAGE_PORT") == "18080"
        else 18080,
        "status": "preparing",
    }


def registration(state, marker):
    directory = state_directory(state["project"], state.get("base_owner"))
    journal = directory / "registration.json"
    if state.get("registered") and not journal.exists():
        verify_registration(state, marker, bootstrap._read_compose_env())
        return
    if not journal.exists():
        persisted = bootstrap._read_compose_env()
        if any(persisted.get(key) is not None for key in CONFIG_KEYS):
            raise OnlyofficeError(
                "Unowned ONLYOFFICE identity keys already exist; refusing to adopt them."
            )
        atomic_json(
            journal,
            {
                "format": 1,
                "project": state["project"],
                "owner": state["owner"],
                "engine": state["engine"],
                "base_owner": state.get("base_owner"),
                "old": {key: persisted.get(key) for key in CONFIG_KEYS},
                "new": state["config"],
                "base_config": (marker or {}).get("config"),
                "phase": "prepared",
            },
        )
    recover_registration(state, marker)


def recover_registration(state, marker):
    journal = (
        state_directory(state["project"], state.get("base_owner")) / "registration.json"
    )
    if not journal.exists():
        return
    checked_path(journal, private=True)
    value = json.loads(journal.read_text(encoding="utf-8"))
    if (
        value.get("format") != 1
        or any(
            value.get(key) != state.get(key)
            for key in ("project", "owner", "engine", "base_owner")
        )
        or value.get("new") != state["config"]
    ):
        raise OnlyofficeError(
            "The ONLYOFFICE registration journal belongs to another environment."
        )
    observed = {key: bootstrap._read_compose_env().get(key) for key in CONFIG_KEYS}
    if observed not in (value["old"], value["new"]):
        raise OnlyofficeError(
            "The saved ONLYOFFICE identity changed outside its registration journal."
        )
    if marker:
        before = value.get("base_config")
        after = {**before, **state["config"]}
        if marker["config"] not in (before, after):
            raise OnlyofficeError(
                "The base environment changed outside its ONLYOFFICE registration journal."
            )
        marker["config"] = after
        bootstrap._write_marker(marker)
    elif value.get("base_config") is not None:
        raise OnlyofficeError(
            "The base ownership marker disappeared during ONLYOFFICE registration."
        )
    bootstrap._write_compose_env(state["config"])
    state["registered"] = True
    save(state)
    journal.unlink()


def inspect_resource(kind, name):
    result = run(["docker", kind, "inspect", name], check=False)
    if result.returncode:
        error = result.stderr.lower()
        missing = f"no such {kind}" in error or (
            ("not found" in error or "does not exist" in error) and kind in error
        )
        operational = any(
            message in error
            for message in (
                "permission denied",
                "access denied",
                "cannot connect",
                "connection refused",
                "timeout",
                "unauthorized",
                "forbidden",
            )
        )
        if missing and not operational:
            return None
        raise OnlyofficeError(
            "Cannot inspect local resource ownership; the engine failed or refused access. No missing resource was inferred."
        )
    values = json.loads(result.stdout)
    return values[0] if values else None


def assert_resource(resource, state, kind):
    labels = bootstrap._labels(resource, kind)
    if (
        labels.get("com.docker.compose.project") != state["project"]
        or labels.get(OWNER_LABEL) != state["owner"]
    ):
        raise OnlyofficeError(
            "An ONLYOFFICE resource has unknown ownership; no resource was adopted."
        )
    if (
        state.get("base_owner")
        and labels.get(bootstrap.OWNER_LABEL) != state["base_owner"]
    ):
        raise OnlyofficeError(
            "An ONLYOFFICE resource belongs to another bootstrap generation."
        )


def resources(state, *, preparing=False, inspect_policy=True):
    for container in bootstrap._resources(state["project"])["containers"]:
        if (
            bootstrap._labels(container, "containers").get("com.docker.compose.service")
            in SERVICES
        ):
            assert_resource(container, state, "containers")
    missing = []
    for name in optional_volume_names(state["config"]):
        volume = inspect_resource("volume", name)
        if volume:
            assert_resource(volume, state, "volumes")
        else:
            missing.append(name)
    if missing and not preparing:
        raise OnlyofficeError(
            "Completed ONLYOFFICE storage is missing; preserve the remaining data and recover this addon explicitly."
        )
    network = inspect_resource("network", state["project"] + "_onlyoffice")
    if network:
        assert_resource(network, state, "networks")
        if inspect_policy:
            assert_network_policy(network, state.get("provider"))
    return missing, network


def labels(state):
    result = [
        "--label",
        f"com.docker.compose.project={state['project']}",
        "--label",
        f"{OWNER_LABEL}={state['owner']}",
    ]
    if state.get("base_owner"):
        result += ["--label", f"{bootstrap.OWNER_LABEL}={state['base_owner']}"]
    return result


def create_resources(state, *, allow_volumes=False):
    missing, network = resources(state, preparing=True)
    if missing and not allow_volumes:
        raise OnlyofficeError(
            "Completed ONLYOFFICE storage is missing; it will not be recreated."
        )
    for name in missing:
        run(["docker", "volume", "create", *labels(state), name])
    if not network:
        arguments = [
            "docker",
            "network",
            "create",
            "--internal",
            *labels(state),
            "--label",
            "com.docker.compose.network=onlyoffice",
        ]
        engine = run(["docker", "info", "--format", "{{json .}}"])
        info = json.loads(engine.stdout)
        state["provider"] = "podman" if "host" in info else "docker"
        save(state)
        for key, value in network_driver_options(state["provider"]).items():
            arguments += ["--opt", f"{key}={value}"]
        run([*arguments, state["project"] + "_onlyoffice"])


def compose(state, marker, environment, *arguments, timeout=600):
    files = ["-f", str(bootstrap.COMPOSE)]
    if marker:
        files += ["-f", str(bootstrap.OWNED_COMPOSE)]
    files += ["-f", str(SERVER_OVERLAY), "-f", str(OVERLAY)]
    if state.get("base_owner"):
        files += ["-f", str(ROOT / "tools/onlyoffice/compose.owned.yml")]
    return run(
        ["docker", "compose", "-p", state["project"], *files, *arguments],
        environment=runtime_environment(state, environment),
        timeout=timeout,
    )


def runtime_config(state, environment):
    storage = int(environment.get("MEDILAB_GARAGE_PORT", "3900"))
    if storage in (443, state["http_port"]):
        raise OnlyofficeError(
            "The selected Garage port conflicts with the ONLYOFFICE namespace; choose a different owned local environment."
        )
    bucket = environment.get("BUCKET_LABORATORY_NAME", "laboratory-files")
    if (
        environment.get("BUCKET_LABORATORY_ADDRESS", "http://garage:3900")
        != "http://garage:3900"
        or environment.get(
            "BUCKET_LABORATORY_PUBLIC_ADDRESS", f"http://localhost:{storage}"
        )
        != f"http://localhost:{storage}"
    ):
        raise OnlyofficeError(
            "Managed local editing requires the selected local Garage origin; external bucket configuration was not changed."
        )
    if not bucket or not all(
        character.isalnum() or character in "-." for character in bucket
    ):
        raise OnlyofficeError("The selected laboratory bucket name is invalid.")
    return {
        "format": 1,
        "public_origin": f"http://localhost:{state['config']['MEDILAB_ONLYOFFICE_PORT']}",
        "storage_origin": f"http://localhost:{storage}",
        "storage_port": storage,
        "http_port": state["http_port"],
        "bucket": bucket,
    }


def setup():
    project, marker, engine, environment = selection(
        recovering=True, validate_inputs=True, secure_engine=True
    )
    guard_existing(project, read_state(project, marker, engine), environment)
    directory = state_directory(project, (marker or {}).get("owner"))
    checked_path(DIRECTORY)
    if (
        directory.exists()
        and not (directory / "state.json").exists()
        and any(item.name != "operation.lock" for item in directory.iterdir())
    ):
        raise OnlyofficeError(
            "ONLYOFFICE private files exist without their ownership marker; refusing adoption."
        )
    if directory.exists():
        checked_path(directory, private=True)
    else:
        directory.mkdir(parents=True, mode=0o700)
        protect(directory)
    with locked(directory):
        state = read_state(project, marker, engine)
        if state and state["status"] == "completed":
            resources(state)
            recover_registration(state, marker)
            verify_registration(state, marker, bootstrap._read_compose_env())
        else:
            if not state:
                for kind, items in bootstrap._resources(project).items():
                    for resource in items:
                        if addon_resource(resource, kind, project):
                            raise OnlyofficeError(
                                "Unowned ONLYOFFICE resources already exist in this project; no resources were adopted."
                            )
                state = new_state(project, marker, engine)
                save(state)
            registration(state, marker)
            if marker:
                environment = bootstrap._compose_environment(
                    project, marker["owner"], marker["config"]
                )
            from onlyoffice_tls import prepare

            prepare(directory, project, state["owner"])
            jwt = checked_path(directory / "jwt", private=True)
            if not jwt.exists():
                if state.get("material"):
                    raise OnlyofficeError(
                        "Prepared ONLYOFFICE secret material is missing; it will not be regenerated."
                    )
                descriptor, temporary = tempfile.mkstemp(prefix=".jwt-", dir=directory)
                try:
                    with os.fdopen(descriptor, "w", encoding="ascii") as output:
                        output.write(
                            environment.get("ONLYOFFICE_JWT_SECRET")
                            or secrets.token_urlsafe(48)
                        )
                        output.flush()
                        os.fsync(output.fileno())
                    protect(Path(temporary))
                    os.link(temporary, jwt)
                finally:
                    Path(temporary).unlink(missing_ok=True)
            expected = runtime_config(state, environment)
            config_file = directory / "runtime.json"
            if config_file.exists():
                if json.loads(config_file.read_text()) != expected:
                    raise OnlyofficeError(
                        "The prepared ONLYOFFICE endpoint configuration changed; existing identities were preserved."
                    )
            else:
                atomic_json(config_file, expected)
            material = material_fingerprints(directory)
            if state.get("material") and state["material"] != material:
                raise OnlyofficeError(
                    "Prepared ONLYOFFICE secret material changed outside its ownership state."
                )
            state["material"] = material
            save(state)
        from onlyoffice_tls import verify

        verify(directory)
        if json.loads(
            (directory / "runtime.json").read_text(encoding="utf-8")
        ) != runtime_config(state, environment):
            raise OnlyofficeError(
                "The selected local endpoint configuration differs from the owned editor configuration."
            )
        create_resources(state, allow_volumes=state["status"] != "completed")
        compose(state, marker, environment, "config", "--quiet")
        handoff_public_port(state, marker, environment)
        try:
            compose(state, marker, environment, "up", "-d", "--wait", *SERVICES)
            verify_network(state, marker, environment)
        except Exception:
            stop(state, marker, environment)
            raise
        guard_existing(project, state, environment)
        compose(state, marker, environment, "up", "-d", "--no-deps", "odoo")
        verify_runtime(state, marker, environment)
        state["status"] = "completed"
        save(state)
    print(
        f"ONLYOFFICE setup and integration verification completed: http://localhost:{state['config']['MEDILAB_ONLYOFFICE_PORT']}."
    )


def stop(state, marker, environment):
    owned = owned_containers(state)
    for service in ("onlyoffice", "onlyoffice-adapter", "onlyoffice-gateway"):
        ids = [
            peer["Id"]
            for peer in owned
            if bootstrap._labels(peer, "containers").get("com.docker.compose.service")
            == service
        ]
        if ids:
            run(
                [
                    "docker",
                    "stop",
                    "--time",
                    "1890" if service == "onlyoffice" else "10",
                    *ids,
                ],
                timeout=1950,
            )


@contextlib.contextmanager
def drained_for_compose(project, marker, environment):
    state = read_state(project, marker)
    if not state or state.get("engine") != bootstrap._assert_local_engine():
        raise OnlyofficeError(
            "The selected editor ownership changed; refusing to stop the base services."
        )
    with locked(state_directory(project, state.get("base_owner"))):
        verify_registration(state, marker, bootstrap._read_compose_env())
        resources(state, preparing=True)
        stop(state, marker, environment)
        yield


def remove_owned_containers(state):
    return onlyoffice_lifecycle.remove_containers(sys.modules[__name__], state)


def handoff_public_port(state, marker, environment):
    return onlyoffice_lifecycle.handoff_public_port(
        sys.modules[__name__], state, marker, environment
    )


def owned_containers(state):
    selected = [
        peer
        for peer in bootstrap._resources(state["project"])["containers"]
        if bootstrap._labels(peer, "containers").get("com.docker.compose.service")
        in SERVICES
    ]
    for peer in selected:
        assert_resource(peer, state, "containers")
    return selected


def verify_network(state, marker, environment):
    return onlyoffice_checks.verify_network(
        sys.modules[__name__], state, marker, environment
    )


def verify_runtime(state, marker, environment):
    return onlyoffice_checks.verify_runtime(
        sys.modules[__name__], state, marker, environment
    )


def actual_status(state):
    return onlyoffice_checks.actual_status(sys.modules[__name__], state)


def verify_identity(state, marker, environment):
    return onlyoffice_checks.verify_identity(
        sys.modules[__name__], state, marker, environment
    )


def verify_image(state):
    return onlyoffice_checks.verify_image(sys.modules[__name__], state)


def main():
    commands = {
        "setup",
        "recover-registration",
        "guard-existing",
        "up",
        "down",
        "restart",
        "status",
        "logs",
        "verify",
        "config-check",
    }
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        raise SystemExit(__doc__)
    command = sys.argv[1]
    try:
        if command in {"setup", "up", "restart", "verify", "config-check"}:
            virtual = ROOT / "src/core/.venv"
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
                        [str(executable), str(Path(__file__).resolve()), command],
                        cwd=ROOT,
                        check=False,
                    ).returncode
                )
        if command == "setup":
            setup()
            return
        project, marker, engine, environment = selection(
            secure_engine=command in {"up", "restart", "verify", "config-check"},
            recovering=command in {"recover-registration", "guard-existing"},
            validate_inputs=command
            in {"guard-existing", "up", "restart", "verify", "config-check"},
        )
        state = read_state(project, marker, engine)
        if command == "guard-existing":
            guard_existing(project, state, environment)
            return
        if command == "recover-registration":
            if state:
                with locked(state_directory(project, state.get("base_owner"))):
                    recover_registration(state, marker)
            return
        if not state:
            raise OnlyofficeError(
                "ONLYOFFICE has not been prepared for this selection; run task onlyoffice:setup."
            )
        if state["status"] == "completed":
            verify_registration(state, marker, bootstrap._read_compose_env())
        if command == "status":
            status = actual_status(state)
            print(json.dumps(status))
            if not status["ready"]:
                raise SystemExit(1)
            return
        resources(
            state,
            preparing=command in {"logs", "down"},
            inspect_policy=command not in {"logs", "down"},
        )
        if command == "logs":
            for peer in owned_containers(state):
                result = run(["docker", "logs", "--tail", "100", peer["Id"]])
                print(result.stdout, end="")
                print(result.stderr, end="", file=sys.stderr)
            return
        if command in {"up", "restart", "verify", "config-check"}:
            guard_existing(project, state, environment)
            from onlyoffice_tls import verify

            verify(state_directory(project, state.get("base_owner")))
            if json.loads(
                (
                    state_directory(project, state.get("base_owner")) / "runtime.json"
                ).read_text(encoding="utf-8")
            ) != runtime_config(state, environment):
                raise OnlyofficeError(
                    "The selected local endpoint configuration differs from the owned editor configuration."
                )
        if command == "config-check":
            compose(state, marker, environment, "config", "--quiet")
            verify_identity(state, marker, environment)
            print("ONLYOFFICE configuration and ownership are valid.")
            return
        with locked(state_directory(project, state.get("base_owner"))):
            if command == "down":
                stop(state, marker, environment)
                remove_owned_containers(state)
            elif command in {"up", "restart"}:
                if state["status"] != "completed":
                    raise OnlyofficeError(
                        "ONLYOFFICE preparation is incomplete; resume onlyoffice:setup."
                    )
                if command == "restart":
                    stop(state, marker, environment)
                create_resources(state)
                handoff_public_port(state, marker, environment)
                try:
                    compose(state, marker, environment, "up", "-d", "--wait", *SERVICES)
                    verify_network(state, marker, environment)
                except Exception:
                    stop(state, marker, environment)
                    raise
                guard_existing(project, state, environment)
                compose(state, marker, environment, "up", "-d", "--no-deps", "odoo")
            elif command == "verify":
                verify_network(state, marker, environment)
                verify_runtime(state, marker, environment)
                print(
                    "ONLYOFFICE actual conversion, callback refusal and network verification passed."
                )
    except (OnlyofficeError, bootstrap.BootstrapError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
    except (
        OSError,
        ValueError,
        KeyError,
        StopIteration,
        subprocess.CalledProcessError,
    ):
        print(
            "ONLYOFFICE operation refused or failed. Preserve its owned data; inspect onlyoffice:status and retry onlyoffice:setup for a prepared selection.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
