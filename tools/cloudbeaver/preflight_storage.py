"""Select workspace consumers without exposing container environments or Secret content."""

WORKSPACE_FILES = (
    "workspace/.data/cb.h2v2.dat.mv.db",
    "workspace/.data/.cloudbeaver.runtime.conf",
    "workspace/.data/.database-credentials.dat",
)
METADATA_COMMAND = (
    "for file in "
    + " ".join(WORKSPACE_FILES)
    + "; do stat -c '%n|%s|%u|%g|%a' \"$file\" 2>/dev/null || printf 'missing|%s\\n' \"$file\"; done"
)


def workspace_metadata(output):
    lines = (output or "").splitlines()
    present = {line.split("|")[0] for line in lines if len(line.split("|")) == 5}
    for path in WORKSPACE_FILES:
        if path not in present and "missing|" + path not in lines:
            lines.append("missing|" + path)
    return {"available": set(WORKSPACE_FILES) <= present, "file_metadata": lines}


def workspace_consumers(pods, claim):
    result = []
    for pod in pods:
        spec = pod.get("spec", {})
        volumes = {
            volume["name"]: volume["persistentVolumeClaim"].get("readOnly", False)
            for volume in spec.get("volumes", [])
            if volume.get("persistentVolumeClaim", {}).get("claimName") == claim
        }
        if not volumes:
            continue
        mounts = []
        for kind in ("initContainers", "containers", "ephemeralContainers"):
            for container in spec.get(kind, []):
                for mount in container.get("volumeMounts", []):
                    if mount.get("name") in volumes:
                        mounts.append(
                            {
                                "container": container["name"],
                                "kind": kind,
                                "read_only": bool(volumes[mount["name"]] or mount.get("readOnly", False)),
                            }
                        )
        metadata = pod["metadata"]
        result.append(
            {
                "name": metadata["name"],
                "uid": metadata.get("uid"),
                "node": spec.get("nodeName"),
                "phase": pod.get("status", {}).get("phase"),
                "terminating": metadata.get("deletionTimestamp") is not None,
                "owners": [
                    {"kind": owner["kind"], "name": owner["name"]} for owner in metadata.get("ownerReferences", [])
                ],
                "mounts": mounts,
                "has_writable_mount": any(not mount["read_only"] for mount in mounts),
            }
        )
    return result
