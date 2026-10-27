"""Create disposable fixture identities; private CA/signing keys never enter images or shared evidence."""

import hashlib
import json
import re
import subprocess
from pathlib import Path

CA_CERTIFICATE = "ca/ca.crt"
CA_KEY = "ca.key"
SERVER_CERTIFICATE = "tls.crt"
SERVER_KEY = "tls.key"
SHA256_OPTION = "-sha256"


def _openssl(*args):
    result = subprocess.run(["openssl", *map(str, args)], capture_output=True, timeout=30, check=False)
    if result.returncode:
        raise RuntimeError("Fixture certificate operation failed; inspect the private fixture directory.")


def _require_owner(directory, project):
    if directory.is_symlink() or json.loads((directory / "owner.json").read_text()) != {
        "project": project,
        "format": 1,
    }:
        raise ValueError("Refusing unowned fixture TLS directory.")


def _issue_certificate(directory, leaf, name, names):
    leaf.mkdir(parents=True, mode=0o700)
    _openssl(
        "req",
        "-newkey",
        "rsa:2048",
        "-nodes",
        SHA256_OPTION,
        "-subj",
        "/CN=" + name,
        "-keyout",
        leaf / SERVER_KEY,
        "-out",
        leaf / "request.csr",
    )
    (leaf / SERVER_KEY).chmod(0o600)
    extensions = leaf / "extensions"
    extensions.write_text(
        "basicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\nsubjectAltName=" + names + "\n"
    )
    _openssl(
        "x509",
        "-req",
        "-in",
        leaf / "request.csr",
        "-CA",
        directory / CA_CERTIFICATE,
        "-CAkey",
        directory / CA_KEY,
        "-CAcreateserial",
        "-days",
        "2",
        SHA256_OPTION,
        "-extfile",
        extensions,
        "-out",
        leaf / SERVER_CERTIFICATE,
    )
    (leaf / SERVER_CERTIFICATE).chmod(0o644)


def prepare(directory, project):
    directory = Path(directory)
    if directory.exists():
        _require_owner(directory, project)
        _openssl("x509", "-in", directory / CA_CERTIFICATE, "-checkend", "3600", "-noout")
        return
    directory.mkdir(parents=True, mode=0o700)
    (directory / "ca").mkdir(mode=0o755)
    _openssl(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        SHA256_OPTION,
        "-days",
        "2",
        "-subj",
        "/CN=MediLab disposable fixture CA",
        "-keyout",
        directory / CA_KEY,
        "-out",
        directory / CA_CERTIFICATE,
    )
    (directory / CA_KEY).chmod(0o600)
    (directory / CA_CERTIFICATE).chmod(0o644)
    for role, names in {
        "documentserver": "DNS:documentserver",
        "garage": "DNS:garage-tls",
        "loopback": "DNS:localhost,IP:127.0.0.1",
    }.items():
        _issue_certificate(directory, directory / role, role, names)
    (directory / "owner.json").write_text(json.dumps({"project": project, "format": 1}) + "\n")


def prepare_runner(directory, project, hostname):
    directory = Path(directory)
    _require_owner(directory, project)
    if not re.fullmatch(re.escape(project) + r"-acceptance(?:-[a-z0-9-]+)?", hostname):
        raise ValueError("Refusing a runner identity outside this fixture project.")
    leaf = directory / "runners" / hostname
    if leaf.exists():
        raise ValueError("Runner TLS identity already exists; use a fresh guarded runner identity.")
    _issue_certificate(directory, leaf, hostname, "DNS:runner,DNS:" + hostname)


def fingerprint(directory):
    return hashlib.sha256((Path(directory) / CA_CERTIFICATE).read_bytes()).hexdigest()
