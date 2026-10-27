"""Only origin-relative object paths reach the fixed Garage fixture."""

import socket
import ssl
import tempfile
import unittest
from pathlib import Path

from tools.onlyoffice_integration.fixture_tls import prepare
from tools.onlyoffice_integration.loopback_storage_proxy import storage_path


class TestStoragePath(unittest.TestCase):
    def test_signed_object_query_is_preserved(self):
        value = "/laboratory-files/report.docx?signature=fixture"
        self.assertEqual(storage_path(value), value)
        custom = "/laboratory-files-integration-page/report.docx?signature=fixture"
        self.assertEqual(storage_path(custom), custom)

    def test_only_owned_bucket_objects_are_exposed(self):
        for value in (
            "/",
            "/other-bucket/key",
            "/laboratory-files/../admin",
            "/laboratory-files/%2e%2e/admin",
            "/laboratory-files/a%2fb",
            "/laboratory-files/a%5cb",
            "/laboratory-files/a%0ab",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                storage_path(value)

    def test_absolute_targets_and_header_injection_are_refused(self):
        for value in (
            "https://other.example/file",
            "//other.example/file",
            "/\\other.example/file",
            "/a\r\nHost:x",
            "",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                storage_path(value)


class TestIsolatedFixture(unittest.TestCase):
    def test_nested_encoding_and_malformed_targets_are_refused(self):
        for value in (
            "%252e%252e",
            "a%252fb",
            "a%255cb",
            "a%250db",
            "a%00b",
            "a%FFb",
            "bad%xy",
        ):
            with (
                self.subTest(value=value),
                self.assertRaises((ValueError, UnicodeError)),
            ):
                storage_path("/laboratory-files/" + value)
        value = "/laboratory-files/one%20file%25.docx?X-Amz-Signature=A%2FB%2B&url=https%3A%2F%2Fother.example"
        self.assertEqual(storage_path(value), value)

    def test_ambiguous_encoding_is_refused_without_changing_signed_bytes(self):
        for target in (
            "/laboratory-files/report%2edocx",
            "/laboratory-files/report.docx?signature=bad%xy",
            "/laboratory-files/report.docx?signature=raw+space",
            "/laboratory-files/report.docx?signature=raw/slash",
            "/laboratory-files/report.docx?signature=%2f",
        ):
            with self.subTest(target=target), self.assertRaises(ValueError):
                storage_path(target)
        query = "X-Amz-Credential=fixture%2Fgarage&X-Amz-Signature=A%2FB%2B&empty="
        target = "/laboratory-files/report%20one.docx?" + query
        self.assertEqual(storage_path(target), target)

    def test_startup_requires_explicit_fixture_and_container_then_binds_only_loopback(
        self,
    ):
        from unittest.mock import patch

        from tools.onlyoffice_integration import loopback_storage_proxy as proxy

        with (
            patch.dict(proxy.os.environ, {}, clear=True),
            self.assertRaises(RuntimeError),
        ):
            proxy.main()
        with patch.dict(proxy.os.environ, MEDILAB_ONLYOFFICE_STORAGE_FIXTURE="isolated-owned"):
            with (
                patch.object(proxy.os.path, "exists", return_value=False),
                self.assertRaises(RuntimeError),
            ):
                proxy.main()
            with (
                patch.object(proxy.os.path, "exists", return_value=True),
                patch.object(proxy, "LoopbackTLSServer") as server,
                patch.object(proxy, "server_context") as context,
            ):
                proxy.main()
                server.assert_called_once_with(("127.0.0.1", 3900), proxy.Handler, context.return_value)
                server.return_value.serve_forever.assert_called_once()

    def test_real_adapter_forwards_only_valid_objects_to_fixed_garage_authority(self):
        import http.client
        import threading
        from http.server import BaseHTTPRequestHandler
        from unittest.mock import patch

        from tools.onlyoffice_integration import loopback_storage_proxy as proxy

        calls = []
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        tls = Path(directory.name) / "tls"
        prepare(tls, "medilab171-agent4-test-storage")
        trusted = ssl.create_default_context(cafile=str(tls / "ca/ca.crt"))

        def context(role):
            value = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            value.load_cert_chain(tls / role / "tls.crt", tls / role / "tls.key")
            return value

        class Peer(BaseHTTPRequestHandler):
            def do_GET(self):
                calls.append((self.path, dict(self.headers)))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"immutable fixture bytes")

            def log_message(self, *_args):
                pass

        servers = [
            proxy.LoopbackTLSServer(("127.0.0.1", 0), handler, context(role))
            for handler, role in ((Peer, "garage"), (proxy.Handler, "loopback"))
        ]
        for server in servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
        original = http.client.HTTPSConnection

        def garage(host, port, timeout):
            self.assertEqual((host, port, timeout), ("garage-tls", 3900, 30))
            connection = original(host, port, timeout=timeout, context=trusted)
            connection._create_connection = lambda *_args: socket.create_connection(
                ("127.0.0.1", servers[0].server_port), timeout=timeout
            )
            return connection

        with patch.object(proxy, "HTTPSConnection", side_effect=garage):
            for path, host, status in (
                (
                    "/laboratory-files/report.docx?signature=A%2FB",
                    "localhost:3900",
                    200,
                ),
                ("/laboratory-files/%252e%252e/admin", "localhost:3900", 400),
                ("//other.example/path", "localhost:3900", 400),
                ("/laboratory-files/report.docx", "other.example", 400),
            ):
                client = original("127.0.0.1", servers[1].server_port, timeout=3, context=trusted)
                try:
                    client.request(
                        "GET",
                        path,
                        headers={"Host": host, "Authorization": "do-not-forward"},
                    )
                    response = client.getresponse()
                    self.assertEqual(response.status, status)
                    content = response.read()
                    if status == 200:
                        self.assertEqual(content, b"immutable fixture bytes")
                finally:
                    client.close()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "/laboratory-files/report.docx?signature=A%2FB")
        self.assertNotIn("Authorization", calls[0][1])
        untrusted = original(
            "127.0.0.1",
            servers[1].server_port,
            timeout=3,
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        )
        self.addCleanup(untrusted.close)
        with self.assertRaises(ssl.SSLCertVerificationError):
            untrusted.connect()


if __name__ == "__main__":
    unittest.main()
