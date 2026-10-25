"""Count and fingerprint sensitive values in this stack's upstream logs without printing them."""

import hashlib
import re

from .run import compose, require_success, write_result


def scan():
    results = {}
    for name in ("docservice", "converter"):
        response = require_success(compose("exec", "-T", "documentserver", "cat",
            f"/var/log/onlyoffice/documentserver/{name}/out.log"), "Read isolated upstream log")
        tokens = re.findall(r"eyJ[A-Za-z0-9_.-]+", response.stdout)
        capabilities = re.findall(r"/medilab/laboratory-files/callback/([a-zA-Z0-9_-]+)", response.stdout)
        results[name] = {
            "bytes_scanned": len(response.stdout.encode()),
            "jwt_values": len(tokens), "callback_capabilities": len(capabilities),
            "jwt_fingerprints": sorted({hashlib.sha256(value.encode()).hexdigest() for value in tokens}),
            "capability_fingerprints": sorted({hashlib.sha256(value.encode()).hexdigest() for value in capabilities}),
        }
    write_result("upstream-logging.json", results)


if __name__ == "__main__":
    scan()
