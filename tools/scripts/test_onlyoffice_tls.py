"""Exercise real certificate trust, private material retention and failed TLS preparation."""

import hashlib
import json
import os
import socket
import ssl
import tempfile
import threading
import unittest
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import onlyoffice_state
import onlyoffice_tls


class QuietHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"verified")

    def log_message(self, *_args):
        return


class OnlyofficeTlsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="medilab TLS ")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "selection"
        onlyoffice_tls.prepare(self.directory, "medilab-test", "owner-test")
        self.tls = self.directory / "tls"

    def fingerprints(self):
        return {
            path.relative_to(self.tls).as_posix(): (
                hashlib.sha256(path.read_bytes()).hexdigest(),
                path.stat().st_mtime_ns,
            )
            for path in self.tls.rglob("*")
            if path.is_file()
        }

    def test_repeat_and_readonly_verification_preserve_all_material(self):
        before = self.fingerprints()
        onlyoffice_tls.prepare(self.directory, "medilab-test", "owner-test")
        onlyoffice_tls.verify(self.directory)
        self.assertEqual(before, self.fingerprints())
        self.assertEqual(set(before), set(onlyoffice_tls.FILES))
        self.assertNotIn(b"PRIVATE KEY", (self.tls / "public/bundle.crt").read_bytes())

    def test_actual_tls_trust_and_hostname_validation(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(
            self.tls / "server/tls.crt", self.tls / "server/tls.key"
        )
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            trusted = ssl.create_default_context(
                cafile=str(self.tls / "public/bundle.crt")
            )
            with (
                socket.create_connection(server.server_address, timeout=3) as transport,
                trusted.wrap_socket(transport, server_hostname="onlyoffice") as stream,
            ):
                stream.sendall(
                    b"GET / HTTP/1.1\r\nHost: onlyoffice\r\nConnection: close\r\n\r\n"
                )
                self.assertIn(b"200 OK", stream.recv(4096))
            with socket.create_connection(
                server.server_address, timeout=3
            ) as transport:
                with self.assertRaises(ssl.SSLCertVerificationError):
                    trusted.wrap_socket(transport, server_hostname="foreign.example")
            untrusted = ssl.create_default_context()
            with socket.create_connection(
                server.server_address, timeout=3
            ) as transport:
                with self.assertRaises(ssl.SSLCertVerificationError):
                    untrusted.wrap_socket(transport, server_hostname="onlyoffice")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive())

    def test_wrong_project_or_owner_cannot_replace_material(self):
        before = self.fingerprints()
        for project, owner in (
            ("other-project", "owner-test"),
            ("medilab-test", "other-owner"),
        ):
            with self.subTest(project=project, owner=owner):
                with self.assertRaises(onlyoffice_state.OnlyofficeError):
                    onlyoffice_tls.prepare(self.directory, project, owner)
                self.assertEqual(before, self.fingerprints())

    def test_partial_committed_state_is_not_regenerated(self):
        (self.tls / "server/tls.key").unlink()
        before = self.fingerprints()
        with self.assertRaises(onlyoffice_state.OnlyofficeError):
            onlyoffice_tls.prepare(self.directory, "medilab-test", "owner-test")
        self.assertEqual(before, self.fingerprints())
        self.assertFalse((self.tls / "server/tls.key").exists())

    def test_expired_certificate_is_rejected_without_replacement(self):
        before = self.fingerprints()
        expired = onlyoffice_tls._now() + timedelta(days=onlyoffice_tls.SERVER_DAYS + 1)
        with (
            mock.patch.object(onlyoffice_tls, "_now", return_value=expired),
            self.assertRaises(onlyoffice_state.OnlyofficeError),
        ):
            onlyoffice_tls.prepare(self.directory, "medilab-test", "owner-test")
        self.assertEqual(before, self.fingerprints())

    def test_mismatched_server_key_is_rejected_without_replacement(self):
        (self.tls / "server/tls.key").write_bytes((self.tls / "ca.key").read_bytes())
        before = self.fingerprints()
        with self.assertRaises(onlyoffice_state.OnlyofficeError):
            onlyoffice_tls.verify(self.directory)
        self.assertEqual(before, self.fingerprints())

    def test_public_root_bundle_must_retain_public_roots(self):
        (self.tls / "public/bundle.crt").write_bytes(
            (self.tls / "public/ca.crt").read_bytes()
        )
        with self.assertRaises(onlyoffice_state.OnlyofficeError):
            onlyoffice_tls.verify(self.directory)

    def test_every_original_system_root_is_recorded_and_retained(self):
        expected = {
            hashlib.sha256(cert).hexdigest()
            for cert in ssl.create_default_context().get_ca_certs(binary_form=True)
        }
        manifest = json.loads((self.tls / "public-roots.json").read_text())
        self.assertEqual(set(manifest["roots"]), expected)
        onlyoffice_tls.verify(self.directory)

    def test_a_leaf_certificate_does_not_substitute_for_public_trust_roots(self):
        replacement = (self.tls / "public/ca.crt").read_bytes() + (
            self.tls / "server/tls.crt"
        ).read_bytes()
        (self.tls / "public/bundle.crt").write_bytes(replacement)
        with self.assertRaises(onlyoffice_state.OnlyofficeError):
            onlyoffice_tls.verify(self.directory)

    def test_unexpected_files_are_not_exposed_by_mounted_certificate_directories(self):
        for relative in ("public/unexpected.key", "server/unexpected.key"):
            with self.subTest(relative=relative):
                path = self.tls / relative
                contents = (self.tls / "ca.key").read_bytes()
                path.write_bytes(contents)
                try:
                    with self.assertRaises(onlyoffice_state.OnlyofficeError):
                        onlyoffice_tls.verify(self.directory)
                    self.assertEqual(path.read_bytes(), contents)
                finally:
                    path.unlink()

    def test_private_material_in_public_files_is_rejected_without_leaking_it(self):
        private_key = (self.tls / "ca.key").read_bytes()
        for relative in ("server/tls.crt", "public/ca.crt", "public/bundle.crt"):
            with self.subTest(relative=relative):
                path = self.tls / relative
                original = path.read_bytes()
                path.write_bytes(original + private_key)
                try:
                    with self.assertRaises(onlyoffice_state.OnlyofficeError) as result:
                        onlyoffice_tls.verify(self.directory)
                    self.assertNotIn(private_key.decode(), str(result.exception))
                finally:
                    path.write_bytes(original)

    def test_unexpected_service_names_are_rejected(self):
        other = Path(self.temporary.name) / "different SAN"
        with mock.patch.object(onlyoffice_tls, "DNS_NAMES", {"unapproved"}):
            onlyoffice_tls.prepare(other, "medilab-test", "owner-test")
        with self.assertRaises(onlyoffice_state.OnlyofficeError):
            onlyoffice_tls.verify(other)

    def test_signature_tampering_is_rejected(self):
        x509, _hashes, serialization, *_rest = onlyoffice_tls._crypto()
        path = self.tls / "server/tls.crt"
        certificate = x509.load_pem_x509_certificate(path.read_bytes())
        corrupted = bytearray(certificate.public_bytes(serialization.Encoding.DER))
        corrupted[-1] ^= 1
        path.write_bytes(
            x509.load_der_x509_certificate(bytes(corrupted)).public_bytes(
                serialization.Encoding.PEM
            )
        )
        with self.assertRaises(onlyoffice_state.OnlyofficeError):
            onlyoffice_tls.verify(self.directory)

    def test_missing_required_extensions_fail_with_safe_typed_error(self):
        x509, hashes, serialization, *_rest = onlyoffice_tls._crypto()
        path = self.tls / "server/tls.crt"
        original = path.read_bytes()
        certificate = x509.load_pem_x509_certificate(original)
        key = serialization.load_pem_private_key(
            (self.tls / "ca.key").read_bytes(), password=None
        )
        for omitted in (
            x509.BasicConstraints,
            x509.SubjectAlternativeName,
            x509.ExtendedKeyUsage,
        ):
            with self.subTest(extension=omitted.__name__):
                builder = (
                    x509.CertificateBuilder()
                    .subject_name(certificate.subject)
                    .issuer_name(certificate.issuer)
                    .public_key(certificate.public_key())
                    .serial_number(certificate.serial_number)
                    .not_valid_before(certificate.not_valid_before)
                    .not_valid_after(certificate.not_valid_after)
                )
                for extension in certificate.extensions:
                    if not isinstance(extension.value, omitted):
                        builder = builder.add_extension(
                            extension.value, extension.critical
                        )
                path.write_bytes(
                    builder.sign(key, hashes.SHA256()).public_bytes(
                        serialization.Encoding.PEM
                    )
                )
                try:
                    with self.assertRaises(onlyoffice_state.OnlyofficeError):
                        onlyoffice_tls.verify(self.directory)
                finally:
                    path.write_bytes(original)

    def test_failed_initial_preparation_publishes_no_partial_tree_and_can_retry(self):
        directory = Path(self.temporary.name) / "interrupted"
        with (
            mock.patch.object(
                onlyoffice_tls,
                "_validate",
                side_effect=ValueError("interrupted before publication"),
            ),
            self.assertRaisesRegex(ValueError, "interrupted"),
        ):
            onlyoffice_tls.prepare(directory, "medilab-test", "owner-test")
        self.assertFalse((directory / "tls").exists())
        self.assertEqual(list(directory.iterdir()), [])
        onlyoffice_tls.prepare(directory, "medilab-test", "owner-test")
        onlyoffice_tls.verify(directory)

    def test_missing_system_roots_fail_before_key_generation(self):
        directory = Path(self.temporary.name) / "missing trust"
        with mock.patch.object(onlyoffice_tls.ssl, "create_default_context") as context:
            context.return_value.get_ca_certs.return_value = []
            with self.assertRaisesRegex(
                onlyoffice_state.OnlyofficeError, "trusted system CA"
            ):
                onlyoffice_tls.prepare(directory, "medilab-test", "owner-test")
        self.assertFalse((directory / "tls").exists())
        self.assertEqual(list(directory.iterdir()), [])

    def test_readonly_verification_never_creates_missing_state(self):
        missing = Path(self.temporary.name) / "missing state"
        with self.assertRaises(onlyoffice_state.OnlyofficeError):
            onlyoffice_tls.verify(missing)
        self.assertFalse(missing.exists())

    def test_private_file_protection_is_checked(self):
        key = self.tls / "ca.key"
        if os.name == "nt":
            onlyoffice_state.checked_path(key, private=True)
            onlyoffice_tls.verify(self.directory)
        else:
            key.chmod(0o644)
            with self.assertRaises(onlyoffice_state.OnlyofficeError):
                onlyoffice_tls.verify(self.directory)


if __name__ == "__main__":
    unittest.main()
