"""Fail closed unless every running fixture peer belongs only to its owned internal bridge."""


def validate_plan(config, project):
    network = config.get("networks", {}).get("default", {})
    if network.get("external") is not True or network.get("name") != project + "_default":
        raise ValueError("The fixture requires its precreated, owned internal default network.")
    for service in config.get("services", {}).values():
        if service.get("ports") or service.get("network_mode") or service.get("privileged"):
            raise ValueError("Fixture services cannot publish ports or bypass network isolation.")
        if set(service.get("networks", {"default": {}})) != {"default"}:
            raise ValueError("Fixture services must use only their internal default network.")


def validate_network(project, metadata):
    name = metadata.get("Name", metadata.get("name"))
    labels = metadata.get("Labels", metadata.get("labels", {})) or {}
    internal = metadata.get("Internal", metadata.get("internal"))
    driver = metadata.get("Driver", metadata.get("driver"))
    options = metadata.get("Options", metadata.get("options", {})) or {}
    if name != project + "_default" or labels.get("com.docker.compose.project") != project:
        raise ValueError("The network must belong to this fixture project.")
    if internal is not True or driver != "bridge" or options.get("isolate") != "strict":
        raise ValueError("The running fixture bridge must block routing to and from other bridges.")
    return name


def validate_member(project, network, container):
    config, host = container["Config"], container["HostConfig"]
    labels = config.get("Labels") or {}
    owner = labels.get("com.docker.compose.project", labels.get("medilab.integration.project"))
    if owner != project:
        raise ValueError("Every network peer must have verified fixture ownership.")
    if set(container["NetworkSettings"]["Networks"]) != {network}:
        raise ValueError("A fixture peer cannot bridge another network.")
    if host.get("PortBindings") or any(container["NetworkSettings"].get("Ports", {}).values()):
        raise ValueError("Fixture peers cannot publish host ports.")
    if host.get("NetworkMode") == "host" or host.get("PidMode") == "host" or host.get("Privileged"):
        raise ValueError("Fixture peers cannot share privileged host namespaces.")
    if {str(cap).upper().removeprefix("CAP_") for cap in host.get("CapAdd") or []} & {
        "NET_ADMIN",
        "SYS_ADMIN",
        "ALL",
    }:
        raise ValueError("Fixture peers cannot change network namespaces.")
    if any(
        str(mount.get(part, "")).endswith(("docker.sock", "podman.sock", "containerd.sock"))
        for mount in container.get("Mounts", [])
        for part in ("Source", "Destination")
    ):
        raise ValueError("Fixture peers cannot access the container engine.")
    return {
        "name": container["Name"].lstrip("/"),
        "single_owned_network": True,
        "published_ports": False,
    }


def validate_runtime(project, network, containers):
    name = validate_network(project, network)
    if not containers:
        raise ValueError("No running fixture members were found.")
    return {
        "internal": True,
        "members": [validate_member(project, name, member) for member in containers],
    }
