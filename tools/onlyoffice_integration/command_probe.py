"""Read-only probes of the pinned server's command API, inside the isolated test network."""

import json
import sys
import time

import jwt
import requests

SECRET = "test-secret-of-the-editing-service-0123456789"
URL = "https://documentserver/command"


def probe():
    results = {}
    for name, secret, lifetime, expected in (
        ("valid", SECRET, 300, 0),
        ("invalid_signature", "different-harness-secret-01234567890123456789", 300, 6),
        ("expired", SECRET, -3600, 7),
        ("missing", None, 300, 6),
    ):
        payload = {"c": "version"}
        body = dict(payload)
        if secret:
            body["token"] = jwt.encode({**payload, "exp": int(time.time()) + lifetime}, secret, algorithm="HS256")
        response = requests.post(URL, json=body, timeout=10)
        answer = response.json()
        results[name] = {"http": response.status_code, "error": answer.get("error"), "version": answer.get("version")}
        if response.status_code != 200 or answer.get("error") != expected:
            raise AssertionError("Unexpected command authentication result for " + name)
    payload = {"c": "getForgottenList"}
    response = requests.post(
        URL,
        json={**payload, "token": jwt.encode({**payload, "exp": int(time.time()) + 300}, SECRET, algorithm="HS256")},
        timeout=10,
    )
    answer = response.json()
    results["forgotten_list"] = {
        "http": response.status_code,
        "error": answer.get("error"),
        "count": len(answer.get("keys", [])),
    }
    if response.status_code != 200 or answer.get("error") != 0:
        raise AssertionError("The authenticated forgotten-list command failed")
    return results


if __name__ == "__main__":
    sys.stdout.write(json.dumps(probe(), indent=2) + "\n")
