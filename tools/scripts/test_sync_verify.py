import http.server
import json
import threading
import unittest
from unittest.mock import patch

import sync_verify
from host_tools import HostError


class SyncApiTest(unittest.TestCase):
    def test_base_path_and_no_credentials_are_preserved_by_contract_probes(self):
        observed = []

        def request(url, headers=None):
            observed.append((url, headers))
            if url.endswith("/devices"):
                return (
                    401,
                    {
                        "error": {
                            "code": "invalid_key",
                            "message": "Sign this computer in.",
                        }
                    },
                    {"WWW-Authenticate": "Bearer"},
                )
            return (
                200,
                {"status": "pass", "checks": {"database": "pass", "storage": "pass"}},
                {},
            )

        self.assertEqual(
            sync_verify.verify("http://localhost:8069/prefix/", request),
            "http://localhost:8069/prefix",
        )
        self.assertEqual(len(observed), 4)
        self.assertTrue(
            all(
                (
                    url.startswith("http://localhost:8069/prefix/medilab/api/v1/")
                    for url, _headers in observed
                )
            )
        )
        self.assertEqual(observed[2][1], {})
        self.assertEqual(
            observed[3][1], {"Authorization": "Bearer medilab-setup-invalid-probe"}
        )
        self.assertTrue(
            all((not headers or "Cookie" not in headers for _url, headers in observed))
        )

    def test_unsafe_or_remote_origins_fail_before_network_access(self):
        for value in (
            "http://user:password@localhost:8069",
            "http://localhost:8069?secret=x",
            "http://localhost:8069#x",
            "http://localhost:8069/a/../b",
            "http://localhost:8069/%2e%2e",
            "http://localhost:8069/%2fadmin",
            "http://localhost:8069\\admin",
            "http://localhost:8069/line\nbreak",
            "https://example.com",
            "file:///tmp/data",
            "http://localhost:99999",
            "http://[::1",
            "http://localhost:0",
        ):
            with (
                self.subTest(value=value),
                patch.object(sync_verify, "request_json") as request,
            ):
                with self.assertRaises(HostError):
                    sync_verify.validate_url(value)
                request.assert_not_called()
        self.assertEqual(
            sync_verify.validate_url("https://[::1]:8069/prefix"),
            "https://[::1]:8069/prefix",
        )

    def test_generic_or_failed_health_is_not_api_readiness(self):
        for status, body in (
            (200, {}),
            (200, {"status": "ok"}),
            (302, {"status": "pass"}),
            (503, {"status": "fail"}),
        ):
            with self.subTest(status=status, body=body), self.assertRaises(HostError):
                sync_verify.verify(
                    "http://localhost:8069",
                    lambda *_args, response=(status, body, {}): response,
                )

    def test_readiness_requires_successful_named_checks(self):
        for checks in ({}, {"database": "fail"}, {"database": True}, None):
            with (
                self.subTest(checks=checks),
                self.assertRaisesRegex(HostError, "readiness"),
            ):
                sync_verify.verify(
                    "http://localhost:8069",
                    lambda *_args, current=checks: (
                        200,
                        {"status": "pass", "checks": current},
                        {},
                    ),
                )

    def test_generic_401_wrong_code_or_missing_challenge_fails(self):
        refusals = (
            (401, {}, {"WWW-Authenticate": "Bearer"}),
            (
                401,
                {"error": {"code": "invalid_credentials", "message": "Wrong user"}},
                {"WWW-Authenticate": "Bearer"},
            ),
            (
                401,
                {"error": {"code": "invalid_key", "message": ""}},
                {"WWW-Authenticate": "Bearer"},
            ),
            (401, {"error": {"code": "invalid_key", "message": "Sign in"}}, {}),
            (
                200,
                {"error": {"code": "invalid_key", "message": "Sign in"}},
                {"WWW-Authenticate": "Bearer"},
            ),
        )
        for refusal in refusals:

            def request(url, _headers=None, expected=refusal):
                return (
                    expected
                    if url.endswith("/devices")
                    else (200, {"status": "pass", "checks": {"database": "pass"}}, {})
                )

            with (
                self.subTest(refusal=refusal),
                self.assertRaisesRegex(HostError, "Bearer/invalid_key"),
            ):
                sync_verify.verify("http://localhost:8069", request)

    def _server(self, response):
        observed = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                observed.append((self.path, dict(self.headers)))
                status, headers, body = response(self.path)
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def stop():
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())

        self.addCleanup(stop)
        return (f"http://127.0.0.1:{server.server_port}", observed)

    def test_actual_http_json_probes_bypass_environment_proxy_and_send_no_cookies(self):

        def response(url):
            if url.endswith("/devices"):
                return (
                    401,
                    {"Content-Type": "application/json", "WWW-Authenticate": "Bearer"},
                    json.dumps(
                        {"error": {"code": "invalid_key", "message": "Sign in"}}
                    ).encode(),
                )
            return (
                200,
                {"Content-Type": "application/json"},
                json.dumps({"status": "pass", "checks": {"database": "pass"}}).encode(),
            )

        base, observed = self._server(response)
        with patch.dict(
            sync_verify.urllib.request.os.environ,
            {"HTTP_PROXY": "http://127.0.0.1:1", "NO_PROXY": ""},
        ):
            sync_verify.verify(base + "/prefix")
        self.assertEqual(len(observed), 4)
        self.assertTrue(all(("Cookie" not in headers for _url, headers in observed)))
        self.assertTrue(
            all(
                (
                    url.startswith("/prefix/medilab/api/v1/")
                    for url, _headers in observed
                )
            )
        )

    def test_actual_redirect_is_not_followed_and_html_is_not_parsed_as_success(self):

        def response(url):
            if url == "/redirect":
                return (
                    302,
                    {"Location": "/login", "Content-Type": "text/html"},
                    b"redirect",
                )
            return (200, {"Content-Type": "text/html"}, b"<html>login</html>")

        base, observed = self._server(response)
        with self.assertRaises(HostError):
            sync_verify.request_json(base + "/redirect")
        self.assertEqual([url for url, _headers in observed], ["/redirect"])
        with self.assertRaises(HostError):
            sync_verify.request_json(base + "/login")

    def test_actual_invalid_or_oversized_json_is_rejected(self):
        base, _observed = self._server(
            lambda _url: (
                200,
                {"Content-Type": "application/json"},
                b"x" * (sync_verify.MAX_RESPONSE + 1),
            )
        )
        with self.assertRaises(HostError):
            sync_verify.request_json(base)
        second, _observed = self._server(
            lambda _url: (200, {"Content-Type": "application/json"}, b"invalid")
        )
        with self.assertRaises(HostError):
            sync_verify.request_json(second)


if __name__ == "__main__":
    unittest.main()
