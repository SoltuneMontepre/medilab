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
    sources = {
        f"{worker}-{stream}": f"/var/log/onlyoffice/documentserver/{worker}/{stream}.log"
        for worker in ("docservice", "converter", "example", "metrics")
        for stream in ("out", "err")
    }
    sources.update({f"nginx-{stream}": f"/var/log/nginx/{stream}.log" for stream in ("access", "error")})
    for name, path in [*sources.items(), ("container-output", None)]:
        response = require_success(
            command(
                [*DOCKER, "exec", containers[0], "cat", path] if path else [*DOCKER, "logs", containers[0]],
                env=DOCKER_ENV,
            ),
            "Read isolated upstream log",
        )
        messages = response.stdout + response.stderr
        tokens = re.findall(r"eyJ[A-Za-z0-9_.-]+", messages)
        capabilities = re.findall(r"/medilab/laboratory-files/callback/([a-zA-Z0-9_-]+)", messages)
        results[name] = {
            "status": "FAIL" if tokens or capabilities else "PASS",
            "bytes_scanned": len(messages.encode()),
            "jwt_values": len(tokens),
            "callback_capabilities": len(capabilities),
            "jwt_fingerprints": sorted({hashlib.sha256(value.encode()).hexdigest() for value in tokens}),
            "capability_fingerprints": sorted({hashlib.sha256(value.encode()).hexdigest() for value in capabilities}),
        }
    write_result("upstream-logging.json", results)
    if any(result["status"] == "FAIL" for result in results.values()):
        raise RuntimeError("Sensitive values detected in isolated service logs; inspect private evidence locally.")


if __name__ == "__main__":
    scan()
