"""Exercise drift refusal inside an explicitly marked disposable ONLYOFFICE container."""

import json
import os
import pwd
import subprocess
import sys
from pathlib import Path

MARKER = Path("/run/medilab-onlyoffice-runtime-fixture")
SETTINGS = Path("/opt/medilab/onlyoffice/settings.json")
RUNTIME = Path("/var/www/onlyoffice/Data/runtime.json")
HEALTH = ["/bin/bash", "/opt/medilab/onlyoffice/healthcheck.sh"]
BINARIES = {
    "docservice": "/var/www/onlyoffice/documentserver/server/DocService/docservice",
    "converter": "/var/www/onlyoffice/documentserver/server/FileConverter/converter",
}


def control(action):
    subprocess.run(
        ["supervisorctl", action, "ds:docservice", "ds:converter"],
        capture_output=True,
        check=True,
        timeout=30,
    )


def healthy():
    return subprocess.run(HEALTH, capture_output=True, timeout=10, check=False).returncode == 0


def worker_pids():
    workers = set()
    for process in Path("/proc").glob("[0-9]*"):
        try:
            if (process / "comm").read_text(encoding="utf-8").strip() in BINARIES:
                workers.add(int(process.name))
        except FileNotFoundError:
            continue
    return workers


def main():
    if (
        os.environ.get("MEDILAB_ONLYOFFICE_RUNTIME_FIXTURE") != "isolated-owned"
        or MARKER.read_text(encoding="utf-8").strip() != "isolated-owned"
        or not healthy()
    ):
        raise RuntimeError("An isolated owned healthy fixture is required")
    original = RUNTIME.read_bytes() if RUNTIME.exists() else None
    metadata = RUNTIME.stat() if original is not None else None
    identity = pwd.getpwnam("ds")
    settings = SETTINGS.read_text(encoding="utf-8")

    def restore():
        if original is None:
            RUNTIME.unlink(missing_ok=True)
        else:
            RUNTIME.write_bytes(original)
            RUNTIME.chmod(metadata.st_mode & 0o777)
            os.chown(RUNTIME, metadata.st_uid, metadata.st_gid)

    def drift():
        RUNTIME.write_text(
            json.dumps({"services": {"CoAuthoring": {"expire": {"files": 86400}}}}),
            encoding="utf-8",
        )
        RUNTIME.chmod(0o600)
        os.chown(RUNTIME, identity.pw_uid, identity.pw_gid)

    before = worker_pids()
    try:
        drift()
        if healthy() or worker_pids() != before:
            raise RuntimeError("Live drift did not refuse readiness while preserving workers")
    finally:
        restore()
    if not healthy():
        raise RuntimeError("Restored fixture is not healthy")

    results = []
    control("stop")
    try:
        drift()
        for name, binary in BINARIES.items():
            result = subprocess.run(
                [
                    "sudo",
                    "-u",
                    "ds",
                    "env",
                    "NODE_ENV=production-linux",
                    "NODE_CONFIG_DIR=/etc/onlyoffice/documentserver",
                    "NODE_CONFIG=" + settings,
                    "PKG_EXECPATH=" + binary,
                    binary,
                    "/opt/medilab/onlyoffice/worker-bootstrap.cjs",
                ],
                capture_output=True,
                timeout=30,
                check=False,
            )
            safe = b"ONLYOFFICE worker initialization refused: effective-policy.\n"
            if result.returncode != 78 or result.stdout or result.stderr != safe:
                raise RuntimeError("Native worker drift refusal was not verified")
            results.append({"worker": name, "status": "PASS", "exit_code": 78, "credential_safe_diagnostic": True})
    finally:
        restore()
        control("start")
    if not healthy():
        raise RuntimeError("Restored workers are not healthy")
    sys.stdout.write(
        json.dumps(
            {
                "status": "PASS",
                "native_runtime_merge_drift": results,
                "live_change_readiness_refused": True,
                "workers_preserved_on_live_change": True,
                "restored": True,
            }
        )
        + "\n"
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
        sys.stderr.write("Native policy drift probe refused or failed; inspect only the isolated fixture.\n")
        sys.exit(1)
