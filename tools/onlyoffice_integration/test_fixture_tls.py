"""Disposable identities are verified and never silently replaced or shared across projects."""

import json
import re
import ssl
import subprocess
import tempfile
import unittest
from pathlib import Path

from .fixture_tls import fingerprint, prepare, prepare_runner

PROJECT = "medilab-onlyoffice-tls-unit"


class TestFixtureTLS(unittest.TestCase):
    def test_owned_certificates_are_reusable_without_replacing_their_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "fixture"
            prepare(directory, PROJECT)
            before = fingerprint(directory)
            key = (directory / "loopback/tls.key").read_bytes()
            prepare(directory, PROJECT)
            self.assertEqual(fingerprint(directory), before)
            self.assertEqual((directory / "loopback/tls.key").read_bytes(), key)
            self.assertEqual((directory / "ca.key").stat().st_mode & 0o777, 0o600)
            self.assertEqual((directory / "loopback/tls.key").stat().st_mode & 0o777, 0o600)
            self.assertNotIn("PRIVATE KEY", (directory / "ca/ca.crt").read_text())

    def test_a_different_owner_cannot_reuse_the_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "owner.json").write_text(json.dumps({"project": "foreign", "format": 1}))
            with self.assertRaises(ValueError):
                prepare(directory, PROJECT)

    def test_runner_identity_is_project_bound_and_never_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "fixture"
            project = PROJECT
            prepare(directory, project)
            hostname = project + "-acceptance-real"
            prepare_runner(directory, project, hostname)
            names = subprocess.check_output(
                [
                    "openssl",
                    "x509",
                    "-in",
                    str(directory / "runners" / hostname / "tls.crt"),
                    "-noout",
                    "-ext",
                    "subjectAltName",
                ],
                text=True,
                timeout=10,
            )
            self.assertEqual(set(re.findall(r"DNS:([^,\s]+)", names)), {"runner", hostname})
            with self.assertRaises(ValueError):
                prepare_runner(directory, project, hostname)
            with self.assertRaises(ValueError):
                prepare_runner(directory, project, "production.example")

    def test_missing_certificates_fail_closed_instead_of_enabling_http(self):
        from unittest.mock import patch

        from . import loopback_storage_proxy

        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.dict(loopback_storage_proxy.os.environ, ONLYOFFICE_FIXTURE_TLS_DIR=temporary),
        ):
            with self.assertRaises(FileNotFoundError):
                loopback_storage_proxy.server_context()
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)
