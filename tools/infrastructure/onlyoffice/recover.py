"""Explicit operator retrieval of forgotten bytes; never replay a callback or alter an Odoo version."""

import argparse
import base64
import hashlib
import hmac
import json
import os
import ssl
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def encoded(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=")


def token(body, secret):
    now = int(time.time())
    claims = {"payload": body, "iat": now, "exp": now + 300}
    content = b".".join(
        encoded(json.dumps(part, separators=(",", ":")).encode()) for part in ({"alg": "HS256", "typ": "JWT"}, claims)
    )
    return (content + b"." + encoded(hmac.digest(secret, content, "sha256"))).decode()


def same_origin(url, origin):
    if any(c.isspace() or not c.isprintable() or c == "\\" for c in url):
        return False
    try:
        target, allowed = urlsplit(url), urlsplit(origin)
        return (
            bool(target.hostname)
            and target.scheme == allowed.scheme == "https"
            and target.hostname == allowed.hostname
            and (target.port or 443) == (allowed.port or 443)
            and not target.username
            and not target.password
            and not target.fragment
        )
    except ValueError:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", required=True)
    parser.add_argument("--ca", required=True)
    parser.add_argument("--secret-file", required=True)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--key")
    args = parser.parse_args()
    parts = urlsplit(args.origin)
    if not same_origin(args.origin, args.origin) or parts.path not in ("", "/") or parts.query:
        raise ValueError("Invalid configured origin")
    secret = Path(args.secret_file).read_bytes().strip()
    if len(secret) < 32:
        raise ValueError("Invalid secret")
    output = Path(args.output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    context = ssl.create_default_context(cafile=args.ca)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        NoRedirect(),
        urllib.request.HTTPSHandler(context=context),
    )
    body = {"c": "getForgotten", "key": args.key} if args.key else {"c": "getForgottenList"}
    request = urllib.request.Request(
        args.origin.rstrip("/") + "/command",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Medilab-Editor-Token": "Bearer " + token(body, secret)},
    )
    with opener.open(request, timeout=30) as response:
        result = json.loads(response.read(1048576))
    if result.get("error") != 0:
        raise ValueError("Command refused or bytes unavailable")
    evidence = {
        "operator": args.operator,
        "document_key": args.key,
        "retrieved_at": int(time.time()),
        "classification": "inventory",
    }
    if args.key:
        url = result.get("url", "")
        if not same_origin(url, args.origin):
            raise ValueError("Refused recovery origin")
        digest, size, started = hashlib.sha256(), 0, time.monotonic()
        with opener.open(url, timeout=30) as response, (output / "document.bin").open("xb") as destination:
            while chunk := response.read(1048576):
                if time.monotonic() - started > 900:
                    raise TimeoutError("Recovery retrieval deadline")
                destination.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        evidence.update(sha256=digest.hexdigest(), size=size, classification="retrieved_unverified")
    else:
        evidence["keys"] = result.get("keys", [])
    (output / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    sys.stdout.write("Recovery evidence written; verify bytes and authorization before restoring.\n")


if __name__ == "__main__":
    os.umask(0o077)
    try:
        main()
    except Exception:
        # Exception text can contain signed URLs. Preserve the protected output for operator review.
        sys.stderr.write("Recovery retrieval failed; review protected evidence and service health.\n")
        sys.exit(1)
