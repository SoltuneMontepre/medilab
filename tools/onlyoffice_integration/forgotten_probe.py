"""Read-only snapshot of actual forgotten Office outputs in the isolated harness fixture."""

import hashlib
import io
import json
import sys
import time
import zipfile
from urllib.parse import urlsplit

import jwt
import requests

SECRET = "test-secret-of-the-editing-service-0123456789"
ORIGIN = "https://documentserver"


def command(operation, **fields):
    payload = {"c": operation, **fields}
    token = jwt.encode({**payload, "exp": int(time.time()) + 300}, SECRET, algorithm="HS256")
    response = requests.post(ORIGIN + "/command", json={**payload, "token": token}, timeout=30)
    if response.status_code != 200:
        raise RuntimeError("Forgotten-file command HTTP failure")
    return response.json()


def read(key):
    answer = command("getForgotten", key=key)
    result = {"key_sha256": hashlib.sha256(key.encode()).hexdigest(), "command_error": answer.get("error")}
    url = answer.get("url")
    if not isinstance(url, str):
        result["bytes_available"] = False
        return result
    target = urlsplit(url)
    if target.scheme != "https" or target.netloc != "documentserver" or target.username or target.password:
        raise RuntimeError("Unexpected forgotten-file origin")
    response = requests.get(url, timeout=30, allow_redirects=False)
    result["download_http"] = response.status_code
    result["bytes_available"] = response.status_code == 200
    if response.status_code == 200:
        data = response.content
        result["sha256"] = hashlib.sha256(data).hexdigest()
        result["size"] = len(data)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            result["marker_present"] = any(
                b"MEDILAB_HARNESS_" in archive.read(name) for name in archive.namelist() if name.endswith(".xml")
            )
    return result


def snapshot():
    listing = command("getForgottenList")
    if listing.get("error") != 0:
        raise RuntimeError("Forgotten-list command failed")
    keys = [value.get("key") if isinstance(value, dict) else value for value in listing.get("keys", [])]
    keys = [value for value in keys if isinstance(value, str)]
    return {
        "at": time.time(),
        "list_error": listing.get("error"),
        "count": len(keys),
        "documents": [read(k) for k in keys],
    }


if __name__ == "__main__":
    try:
        result = snapshot()
    except Exception:
        raise SystemExit("Read-only forgotten probe failed; inspect protected local diagnostics.") from None
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
