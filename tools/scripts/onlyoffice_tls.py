"""Prepare or verify worktree-scoped ONLYOFFICE TLS material without changing host trust.

Called by onlyoffice.py inside the locked core Python environment. Cryptography is loaded only when needed.
"""

import hashlib
import ipaddress
import json
import os
import re
import ssl
import stat
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

FILES = (
    "ca.key",
    "server/tls.crt",
    "server/tls.key",
    "public/ca.crt",
    "public/bundle.crt",
    "public-roots.json",
)
DNS_NAMES = {"onlyoffice", "onlyoffice-gateway"}
CA_DAYS = 3650
SERVER_DAYS = 365


def _state():
    import onlyoffice_state

    return onlyoffice_state


def _crypto():
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    except ImportError:
        raise _state().OnlyofficeError(
            "TLS verification needs the locked core environment. Run `task dev:sync`, then retry the ONLYOFFICE command."
        ) from None
    return x509, hashes, serialization, ec, padding, rsa, ExtendedKeyUsageOID, NameOID


def _identity(project, owner):
    if not project or not owner:
        raise _state().OnlyofficeError(
            "TLS preparation requires a verified project and owner."
        )
    return hashlib.sha256(f"{project}\0{owner}".encode()).hexdigest()


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


def _public_roots():
    roots = ssl.create_default_context().get_ca_certs(binary_form=True)
    if not roots:
        raise _state().OnlyofficeError(
            "No trusted system CA certificates are available; repair Python TLS trust first."
        )
    return b"".join(ssl.DER_cert_to_PEM_cert(cert).encode("ascii") for cert in roots)


def _validation_errors():
    x509, *_rest = _crypto()
    from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm

    return (
        OSError,
        ValueError,
        TypeError,
        InvalidSignature,
        UnsupportedAlgorithm,
        x509.ExtensionNotFound,
        x509.DuplicateExtension,
    )


def _write(path, contents, *, private=False):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(contents)
        stream.flush()
        os.fsync(stream.fileno())
    if private or os.name == "nt":
        _state().protect(path)
    elif os.name != "nt":
        path.chmod(0o644)


def _generate(destination, identity, roots):
    x509, hashes, serialization, _ec, _padding, rsa, usage, names = _crypto()
    now = _now()
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name(
        [
            x509.NameAttribute(names.COMMON_NAME, "MediLab local ONLYOFFICE CA"),
            x509.NameAttribute(names.ORGANIZATIONAL_UNIT_NAME, identity),
        ]
    )
    server_name = x509.Name(
        [
            x509.NameAttribute(names.COMMON_NAME, "onlyoffice"),
            x509.NameAttribute(names.ORGANIZATIONAL_UNIT_NAME, identity),
        ]
    )
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=CA_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, None, None),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    server = (
        x509.CertificateBuilder()
        .subject_name(server_name)
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=SERVER_DAYS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(True, False, True, False, False, False, False, None, None),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([usage.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    *(x509.DNSName(name) for name in sorted(DNS_NAMES)),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    public_ca = ca.public_bytes(serialization.Encoding.PEM)
    for key, relative in ((ca_key, "ca.key"), (server_key, "server/tls.key")):
        _write(
            destination / relative,
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
            private=True,
        )
    _write(
        destination / "server/tls.crt", server.public_bytes(serialization.Encoding.PEM)
    )
    _write(destination / "public/ca.crt", public_ca)
    _write(destination / "public/bundle.crt", roots + public_ca)
    fingerprints = sorted(
        {
            hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
            for cert in x509.load_pem_x509_certificates(roots)
        }
    )
    _write(
        destination / "public-roots.json",
        (
            json.dumps(
                {"format": 1, "identity": identity, "roots": fingerprints},
                sort_keys=True,
            )
            + "\n"
        ).encode(),
        private=True,
    )


def _signature(public_key, certificate):
    _x509, _hashes, _serialization, ec, padding, rsa, _usage, _names = _crypto()
    if isinstance(public_key, rsa.RSAPublicKey):
        if public_key.key_size < 2048:
            raise ValueError("Weak CA key")
        public_key.verify(
            certificate.signature,
            certificate.tbs_certificate_bytes,
            padding.PKCS1v15(),
            certificate.signature_hash_algorithm,
        )
    elif isinstance(public_key, ec.EllipticCurvePublicKey):
        if public_key.key_size < 256:
            raise ValueError("Weak CA key")
        public_key.verify(
            certificate.signature,
            certificate.tbs_certificate_bytes,
            ec.ECDSA(certificate.signature_hash_algorithm),
        )
    else:
        raise TypeError("Unsupported CA key")


def _validate(directory, identity=None):
    x509, _hashes, serialization, ec, _padding, rsa, usage, names = _crypto()
    for parent, expected in (
        (directory, {"ca.key", "server", "public", "public-roots.json"}),
        (directory / "server", {"tls.key", "tls.crt"}),
        (directory / "public", {"ca.crt", "bundle.crt"}),
    ):
        if {entry.name for entry in parent.iterdir()} != expected:
            raise ValueError("Unexpected or missing files in TLS material")
    for name in ("server", "public"):
        _state().checked_path(directory / name, private=os.name == "nt")
    for relative in FILES:
        path = _state().checked_path(
            directory / relative,
            private=relative.endswith(".key")
            or relative == "public-roots.json"
            or os.name == "nt",
        )
        if not path.is_file():
            raise ValueError("Incomplete TLS material")
        if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o022:
            raise ValueError("TLS material must not be writable by other users")
        if not relative.endswith(".key") and b"PRIVATE KEY" in path.read_bytes():
            raise ValueError("Private material in a public certificate file")
    ca = x509.load_pem_x509_certificate((directory / "public/ca.crt").read_bytes())
    server = x509.load_pem_x509_certificate((directory / "server/tls.crt").read_bytes())
    ca_key = serialization.load_pem_private_key(
        (directory / "ca.key").read_bytes(), password=None
    )
    server_key = serialization.load_pem_private_key(
        (directory / "server/tls.key").read_bytes(), password=None
    )
    encoding, key_format = (
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    for key, certificate in ((ca_key, ca), (server_key, server)):
        public_key = key.public_key()
        if not (
            (isinstance(public_key, rsa.RSAPublicKey) and public_key.key_size >= 2048)
            or (
                isinstance(public_key, ec.EllipticCurvePublicKey)
                and public_key.key_size >= 256
            )
        ):
            raise ValueError("Weak or unsupported TLS key")
        if key.public_key().public_bytes(
            encoding, key_format
        ) != certificate.public_key().public_bytes(encoding, key_format):
            raise ValueError("TLS key does not match its certificate")
        if not certificate.not_valid_before <= _now() < certificate.not_valid_after:
            raise ValueError("TLS certificate is not currently valid")
        if certificate.signature_hash_algorithm.name not in (
            "sha256",
            "sha384",
            "sha512",
        ):
            raise ValueError("Weak TLS certificate signature")
    if ca.issuer != ca.subject or server.issuer != ca.subject:
        raise ValueError("Unexpected certificate issuer")
    ca_identity = ca.subject.get_attributes_for_oid(names.ORGANIZATIONAL_UNIT_NAME)
    server_identity = server.subject.get_attributes_for_oid(
        names.ORGANIZATIONAL_UNIT_NAME
    )
    if (
        len(ca_identity) != 1
        or ca_identity != server_identity
        or (identity and ca_identity[0].value != identity)
    ):
        raise ValueError("TLS material belongs to a different selection")
    if not ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
        raise ValueError("Invalid CA constraints")
    if server.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
        raise ValueError("Invalid server constraints")
    if not ca.extensions.get_extension_for_class(x509.KeyUsage).value.key_cert_sign:
        raise ValueError("CA cannot sign certificates")
    if (
        usage.SERVER_AUTH
        not in server.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    ):
        raise ValueError("Server certificate cannot authenticate a server")
    alternatives = server.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value
    if set(alternatives.get_values_for_type(x509.DNSName)) != DNS_NAMES:
        raise ValueError("Invalid service DNS names")
    if set(alternatives.get_values_for_type(x509.IPAddress)) != {
        ipaddress.ip_address("127.0.0.1")
    }:
        raise ValueError("Invalid loopback service address")
    _signature(ca.public_key(), ca)
    _signature(ca.public_key(), server)
    bundle = (directory / "public/bundle.crt").read_bytes()
    if b"PRIVATE KEY" in bundle:
        raise ValueError("Private material in public trust bundle")
    certificates = x509.load_pem_x509_certificates(bundle)
    public_ca = ca.public_bytes(serialization.Encoding.DER)
    if not any(
        cert.public_bytes(serialization.Encoding.DER) == public_ca
        for cert in certificates
    ):
        raise ValueError("Private CA missing from trust bundle")
    if not any(
        cert.public_bytes(serialization.Encoding.DER) != public_ca
        for cert in certificates
    ):
        raise ValueError("Public trust roots missing from trust bundle")
    manifest = json.loads((directory / "public-roots.json").read_text(encoding="utf-8"))
    expected_roots = manifest.get("roots") if isinstance(manifest, dict) else None
    if (
        not isinstance(expected_roots, list)
        or not expected_roots
        or any(
            not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
            for value in expected_roots
        )
        or manifest.get("format") != 1
        or manifest.get("identity") != ca_identity[0].value
    ):
        raise ValueError("Invalid public-root provenance")
    actual_roots = {
        hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
        for cert in certificates
        if cert.public_bytes(serialization.Encoding.DER) != public_ca
    }
    if actual_roots != set(expected_roots):
        raise ValueError("The original public trust roots were not retained")
    ssl.create_default_context(cafile=str(directory / "public/bundle.crt"))


def verify(directory, *, identity=None):
    """Validate existing material without writing files or installing dependencies."""
    directory = _state().checked_path(Path(directory), private=True)
    tls = _state().checked_path(directory / "tls", private=True)
    try:
        _validate(tls, identity)
    except _state().OnlyofficeError:
        raise
    except _validation_errors():
        # Cryptography errors may include sensitive parser inputs; return only an actionable status.
        raise _state().OnlyofficeError(
            "ONLYOFFICE TLS material is incomplete, invalid or expired; inspect the owned selection before recovery."
        ) from None


def prepare(directory, project, owner):
    """Publish a complete TLS tree atomically, or verify and retain the existing one."""
    identity = _identity(project, owner)
    directory = _state().checked_path(Path(directory), private=True)
    if not directory.exists():
        directory.mkdir(parents=True, mode=0o700)
        _state().protect(directory)
    if not directory.is_dir():
        raise _state().OnlyofficeError(
            "ONLYOFFICE TLS state must be an owned directory."
        )
    tls = _state().checked_path(directory / "tls", private=True)
    if tls.exists():
        verify(directory, identity=identity)
        return
    roots = _public_roots()
    with tempfile.TemporaryDirectory(
        prefix=".tls-preparing-", dir=directory
    ) as temporary:
        staged = Path(temporary)
        _state().protect(staged)
        for name in ("server", "public"):
            (staged / name).mkdir(mode=0o755)
            if os.name == "nt":
                _state().protect(staged / name)
        _generate(staged, identity, roots)
        _validate(staged, identity)
        if tls.exists():
            raise _state().OnlyofficeError(
                "Another TLS preparation completed; rerun setup without replacing its material."
            )
        staged.rename(tls)
