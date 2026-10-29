"""Move the owned local public publisher without replacing persistent editor identities."""

import demo_bootstrap as bootstrap
from onlyoffice_state import SERVICES, OnlyofficeError


def remove_containers(controller, state):
    peers = controller.owned_containers(state)
    for service in ("onlyoffice-adapter", "onlyoffice", "onlyoffice-gateway"):
        ids = [
            peer["Id"]
            for peer in peers
            if bootstrap._labels(peer, "containers").get("com.docker.compose.service")
            == service
        ]
        if ids:
            controller.run(["docker", "rm", *ids])


def _bindings(peer, section, key):
    metadata = peer.get(section)
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise OnlyofficeError(
            "The owned publisher binding metadata is invalid; no container was changed."
        )
    mapping = metadata.get(key)
    if mapping is None:
        mapping = {}
    if not isinstance(mapping, dict):
        raise OnlyofficeError(
            "The owned publisher binding metadata is invalid; no container was changed."
        )
    result = {}
    for port, values in mapping.items():
        if values is None or values == []:
            continue
        if (
            not isinstance(port, str)
            or not isinstance(values, list)
            or any(
                not isinstance(value, dict)
                or set(value) != {"HostIp", "HostPort"}
                or not all(isinstance(item, str) for item in value.values())
                for value in values
            )
        ):
            raise OnlyofficeError(
                "The owned publisher binding metadata is invalid; no container was changed."
            )
        result[port] = values
    return result


def _effective_matches(peer, actual, expected):
    running = peer.get("State", {}).get(
        "Running", peer.get("State", {}).get("Status") == "running"
    )
    return actual == expected or (not running and not actual)


def handoff_public_port(controller, state, marker, environment):
    peers = controller.owned_containers(state)
    selected = {}
    for service in SERVICES:
        matches = [
            peer
            for peer in peers
            if bootstrap._labels(peer, "containers").get("com.docker.compose.service")
            == service
        ]
        if len(matches) > 1:
            raise OnlyofficeError(
                "The owned editor publisher layout is ambiguous; no container was changed."
            )
        if matches:
            selected[service] = matches[0]
    if not selected:
        return
    expected = {
        f"{state['http_port']}/tcp": [
            {
                "HostIp": "127.0.0.1",
                "HostPort": state["config"]["MEDILAB_ONLYOFFICE_PORT"],
            }
        ]
    }
    server = selected.get("onlyoffice")
    requested = _bindings(server, "HostConfig", "PortBindings") if server else {}
    effective = _bindings(server, "NetworkSettings", "Ports") if server else {}
    legacy = bool(requested or effective)
    if legacy and (
        requested != expected or not _effective_matches(server, effective, expected)
    ):
        raise OnlyofficeError(
            "The owned editor has an unexpected public binding; no publisher was migrated."
        )
    for service in ("onlyoffice-adapter", "onlyoffice-gateway"):
        peer = selected.get(service)
        if not peer:
            continue
        wanted = {} if service == "onlyoffice-adapter" or legacy else expected
        actual_requested = _bindings(peer, "HostConfig", "PortBindings")
        actual_effective = _bindings(peer, "NetworkSettings", "Ports")
        if service == "onlyoffice-adapter" and actual_effective:
            # Podman reports the server's effective publication on its namespace-sharing adapter.
            if (
                not server
                or peer.get("HostConfig", {}).get("NetworkMode")
                != "container:" + server["Id"]
                or actual_effective != effective
            ):
                raise OnlyofficeError(
                    "The owned adapter has an unexpected public binding; no publisher was migrated."
                )
            actual_effective = {}
        stopped_old_gateway = (
            service == "onlyoffice-gateway"
            and not legacy
            and not actual_requested
            and not actual_effective
            and not peer.get("State", {}).get(
                "Running", peer.get("State", {}).get("Status") == "running"
            )
        )
        if (
            actual_requested != wanted
            or not _effective_matches(peer, actual_effective, wanted)
        ) and not stopped_old_gateway:
            raise OnlyofficeError(
                "The owned proxy has an unexpected public binding; no publisher was migrated."
            )
    if legacy:
        controller.stop(state, marker, environment)
        remove_containers(controller, state)
