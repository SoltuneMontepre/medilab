"""Count and fingerprint sensitive values in this stack's upstream logs without printing them."""

import hashlib
import re

from .run import DOCKER, DOCKER_ENV, PROJECT, command, require_success, write_result


def scan():
    containers = require_success(
        command(
            [
                *DOCKER,
                "ps",
                "-q",
                "--filter",
                "label=com.docker.compose.project=" + PROJECT,
                "--filter",
                "label=com.docker.compose.service=documentserver",
                "--filter",
                "status=running",
            ],
            env=DOCKER_ENV,
        ),
        "Find running upstream server",
    ).stdout.split()
    if len(containers) != 1:
        raise RuntimeError("Expected one running upstream server.")
    results = {}
    for name in ("docservice", "converter"):
        response = require_success(
            command(
                [*DOCKER, "exec", containers[0], "cat", f"/var/log/onlyoffice/documentserver/{name}/out.log"],
                env=DOCKER_ENV,
            ),
            "Read isolated upstream log",
        )
        tokens = re.findall(r"eyJ[A-Za-z0-9_.-]+", response.stdout)
        capabilities = re.findall(r"/medilab/laboratory-files/callback/([a-zA-Z0-9_-]+)", response.stdout)
        results[name] = {
            "bytes_scanned": len(response.stdout.encode()),
            "jwt_values": len(tokens),
            "callback_capabilities": len(capabilities),
            "jwt_fingerprints": sorted({hashlib.sha256(value.encode()).hexdigest() for value in tokens}),
            "capability_fingerprints": sorted({hashlib.sha256(value.encode()).hexdigest() for value in capabilities}),
        }
    write_result("upstream-logging.json", results)


if __name__ == "__main__":
    scan()
