"""Check loopback transport and verifier authority without operating a user stack."""

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import onlyoffice_checks as checks
from onlyoffice_state import OnlyofficeError


class PublicHealthTest(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.status = 200
        self.body = b"true"
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                owner.requests.append((self.path, self.headers.get("Host")))
                self.send_response(owner.status)
                self.send_header("Content-Length", str(len(owner.body)))
                self.send_header("Location", "http://foreign.invalid/collect")
                self.end_headers()
                self.wfile.write(owner.body)

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True
        )
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.assertFalse(self.thread.is_alive())

    def test_fixed_loopback_transport_ignores_proxy_and_preserves_origin_host(self):
        port = self.server.server_port
        with patch.dict(
            os.environ,
            {"HTTP_PROXY": "http://foreign.invalid:9", "NO_PROXY": ""},
        ):
            self.assertTrue(checks.public_health(str(port), timeout=1))
        self.assertEqual(self.requests, [("/healthcheck", f"localhost:{port}")])

    def test_redirect_and_wrong_body_are_rejected_then_health_can_recover(self):
        port = self.server.server_port
        self.status = 302
        self.assertFalse(checks.public_health(port, timeout=1))
        self.assertEqual(len(self.requests), 1)
        self.status = 200
        self.body = b"true but not the exact health answer"
        self.assertFalse(checks.public_health(port, timeout=1))
        self.body = b"true"
        self.assertTrue(checks.public_health(port, timeout=1))
        self.assertEqual(len(self.requests), 3)

    def test_invalid_ports_cannot_construct_a_network_client(self):
        for value in ("80@foreign.invalid", "80/path", "0", "65536", True, 80.5):
            with (
                self.subTest(value=value),
                patch.object(checks, "HTTPConnection") as connection,
                self.assertRaises(OnlyofficeError),
            ):
                checks.public_health(value, timeout=1)
            connection.assert_not_called()

    def test_status_rejects_invalid_saved_port_before_network_access(self):
        state = {
            "project": "medilab-test",
            "status": "completed",
            "config": {"MEDILAB_ONLYOFFICE_PORT": "80@foreign.invalid"},
        }
        controller = SimpleNamespace(assert_resource=Mock())
        with (
            patch.object(
                checks.bootstrap, "_resources", return_value={"containers": []}
            ),
            patch.object(checks, "HTTPConnection") as connection,
            self.assertRaises(OnlyofficeError),
        ):
            checks.actual_status(controller, state)
        connection.assert_not_called()


class VerifierAuthorityTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.runtime = {
            "format": 1,
            "bucket": "laboratory-files",
            "public_origin": "http://localhost:29843",
            "storage_origin": "http://localhost:23900",
            "http_port": 18080,
            "storage_port": 23900,
        }
        self.state = {
            "project": "medilab-test",
            "owner": "a" * 32,
            "config": {"MEDILAB_ONLYOFFICE_PORT": "29843"},
        }
        self.runtime_file = self.directory / "runtime.json"
        self.runtime_file.write_text(json.dumps(self.runtime), encoding="utf-8")
        self.ledger = self.directory / "verification.json"
        self.report = {
            "health": True,
            "conversion": True,
            "jwt": True,
            "callback_refused": True,
            "cleaned": True,
        }
        self.controller = SimpleNamespace(
            ROOT=Path(__file__).resolve().parents[2],
            verify_image=Mock(),
            state_directory=lambda *_args: self.directory,
            checked_path=lambda path, **_kwargs: path,
            runtime_config=lambda *_args: dict(self.runtime),
            atomic_json=lambda path, data: path.write_text(
                json.dumps(data), encoding="utf-8"
            ),
            compose=Mock(return_value=SimpleNamespace(stdout=json.dumps(self.report))),
        )
        self.health = patch.object(checks, "public_health", return_value=True).start()
        self.addCleanup(patch.stopall)

    def test_runtime_mismatch_preserves_journal_without_network_or_storage_operations(
        self,
    ):
        content = json.dumps(
            {
                "project": self.state["project"],
                "owner": self.state["owner"],
                "bucket": self.runtime["bucket"],
                "id": "c" * 32,
            }
        ).encode()
        self.ledger.write_bytes(content)
        changed = {**self.runtime, "public_origin": "http://foreign.invalid"}
        self.runtime_file.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaises(OnlyofficeError):
            checks.verify_runtime(self.controller, self.state, None, {})
        self.health.assert_not_called()
        self.controller.compose.assert_not_called()
        self.assertEqual(self.ledger.read_bytes(), content)
        self.runtime_file.write_text(json.dumps(self.runtime), encoding="utf-8")
        self.controller.compose.side_effect = [
            SimpleNamespace(stdout='{"cleaned":true}'),
            SimpleNamespace(stdout=json.dumps(self.report)),
        ]
        checks.verify_runtime(self.controller, self.state, None, {})
        self.assertFalse(self.ledger.exists())
        self.assertEqual(self.controller.compose.call_count, 2)

    def test_recovery_and_conversion_receive_same_owned_bucket_and_origins(self):
        marker = "b" * 32
        self.ledger.write_text(
            json.dumps(
                {
                    "project": self.state["project"],
                    "owner": self.state["owner"],
                    "bucket": self.runtime["bucket"],
                    "id": marker,
                }
            ),
            encoding="utf-8",
        )
        self.controller.compose.side_effect = [
            SimpleNamespace(stdout='{"cleaned":true}'),
            SimpleNamespace(stdout=json.dumps(self.report)),
        ]
        checks.verify_runtime(self.controller, self.state, None, {})
        cleanup, conversion = self.controller.compose.call_args_list
        expected = (
            self.runtime["bucket"],
            self.runtime["public_origin"],
            self.runtime["storage_origin"],
        )
        self.assertEqual(cleanup.args[-5:], (marker, "cleanup", *expected))
        self.assertEqual(conversion.args[-4:], ("convert", *expected))
        self.assertEqual(len(conversion.args[-5]), 32)
        self.assertFalse(self.ledger.exists())


if __name__ == "__main__":
    unittest.main()
