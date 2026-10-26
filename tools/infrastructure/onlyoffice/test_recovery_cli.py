"""Recovery through a verified ephemeral HTTPS peer; no production credentials or services."""

import hashlib
import hmac
import json
import os
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from base64 import urlsafe_b64decode
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent


class TestRecoveryCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.secret = cls.root / "secret"
        cls.secret.write_bytes(os.urandom(48))
        cls.secret.chmod(0o600)
        cls.cert, key = cls.root / "ca.pem", cls.root / "tls-key.pem"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost",
                "-keyout",
                str(key),
                "-out",
                str(cls.cert),
            ],
            check=True,
            capture_output=True,
            timeout=15,
        )
        cls.body = b"retained immutable recovery bytes"
        cls.commands = []
        cls.on_command = None

        class Peer(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                jwt = self.headers["Medilab-Editor-Token"].removeprefix("Bearer ")
                head, claims, signature = jwt.split(".")
                expected = hmac.digest(
                    cls.secret.read_bytes().strip(),
                    (head + "." + claims).encode(),
                    "sha256",
                )
                if not hmac.compare_digest(expected, urlsafe_b64decode(signature + "==")):
                    self.send_error(403)
                    return
                payload = json.loads(urlsafe_b64decode(claims + "=="))
                if payload["payload"] != body or payload["exp"] - payload["iat"] != 300:
                    self.send_error(403)
                    return
                cls.commands.append(body)
                if cls.on_command:
                    cls.on_command()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"error": 0, "keys": ["retained"], "url": cls.origin + "/bytes"}).encode())

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(cls.body)

            def log_message(self, *_args):
                pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Peer)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cls.cert, key)
        cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
        cls.origin = f"https://localhost:{cls.server.server_port}"
        thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        thread.start()
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.server.shutdown)

    def execute(self, name, *arguments, **environment):
        return subprocess.run(
            [
                sys.executable,
                str(DIRECTORY / "recover.py"),
                "--origin",
                self.origin,
                "--ca",
                str(self.cert),
                "--secret-file",
                str(self.secret),
                "--operator",
                "fixture-operator",
                "--output",
                str(self.root / name),
                *arguments,
            ],
            env=dict(
                os.environ,
                MEDILAB_ONLYOFFICE_RECOVERY_INPUT_ROOTS=str(self.root),
                MEDILAB_ONLYOFFICE_RECOVERY_OUTPUT_ROOTS=str(self.root),
            )
            | environment,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    def test_verified_tls_inventory_and_signed_download(self):
        for name, args in (("inventory", ()), ("retrieval", ("--key", "retained"))):
            result = self.execute(name, *args)
            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = json.loads((self.root / name / "evidence.json").read_bytes())
            self.assertEqual(evidence["operator"], "fixture-operator")
            if args:
                self.assertEqual((self.root / name / "document.bin").read_bytes(), self.body)
                self.assertEqual(evidence["sha256"], hashlib.sha256(self.body).hexdigest())
            else:
                self.assertEqual(evidence["keys"], ["retained"])
            self.assertNotIn("Bearer", result.stdout + result.stderr)
            self.assertNotIn(self.origin, result.stdout + result.stderr)
        self.assertNotEqual(self.execute("inventory").returncode, 0)

    def test_evidence_symlink_injected_after_request_never_overwrites(self):
        sentinel = self.root / "sentinel"
        sentinel.write_bytes(b"preserve")
        type(self).on_command = lambda: (self.root / "race" / "evidence.json").symlink_to(sentinel)
        try:
            result = self.execute("race")
        finally:
            type(self).on_command = None
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_bytes(), b"preserve")
        self.assertTrue((self.root / "race").exists())

    def test_missing_roots_and_outside_output_fail_closed(self):
        result = self.execute(
            "outside",
            MEDILAB_ONLYOFFICE_RECOVERY_OUTPUT_ROOTS=str(self.root / "unconfigured"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "outside").exists())
