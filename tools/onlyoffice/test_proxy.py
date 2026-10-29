"""Observable local proxy boundaries; full Document Server behavior needs actual integration verification."""

import base64
import hashlib
import http.client
import json
import os
import ssl
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import proxy

CONFIG = {
    "public_origin": "http://localhost:29843",
    "storage_origin": "http://localhost:23900",
    "storage_port": 23900,
    "http_port": 18080,
    "bucket": "laboratory-files",
}


class ProxyContractTest(unittest.TestCase):
    def test_gateway_owns_public_listener_and_adapter_has_only_loopback_storage(self):
        for role, expected in (
            (
                "gateway",
                [
                    ("0.0.0.0", 7443),
                    ("0.0.0.0", 9443),
                    ("0.0.0.0", CONFIG["http_port"]),
                ],
            ),
            ("adapter", [("127.0.0.1", CONFIG["storage_port"])]),
        ):
            with (
                self.subTest(role=role),
                patch.dict(os.environ, {"ONLYOFFICE_PROXY_ROLE": role}),
                patch.object(proxy.Path, "read_text", return_value=json.dumps(CONFIG)),
                patch.object(proxy, "Proxy") as server,
                patch.object(proxy.socket, "has_ipv6", False),
                patch.object(proxy.threading, "Thread"),
                patch.object(proxy.threading, "Event"),
            ):
                proxy.main()
            self.assertEqual([call.args[0] for call in server.call_args_list], expected)

    def test_signed_storage_target_and_host_are_not_normalized(self):
        observed = []

        class Backend(BaseHTTPRequestHandler):
            def do_GET(self):
                observed.append(
                    (
                        self.path,
                        self.headers.get("Host"),
                        self.headers.get("Cookie"),
                        self.headers.get("Authorization"),
                    )
                )
                self.send_response(200)
                self.send_header("Content-Length", "5")
                self.end_headers()
                self.wfile.write(b"bytes")

            def log_message(self, *_args):
                return

        backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        self.addCleanup(backend.server_close)
        self.addCleanup(backend.shutdown)
        threading.Thread(target=backend.serve_forever, daemon=True).start()
        context = ssl.create_default_context()
        original = proxy.route

        def selected(config, kind, method, raw, host):
            original(config, kind, method, raw, host)
            return "http", "127.0.0.1", backend.server_port

        with (
            patch.object(proxy.ssl, "create_default_context", return_value=context),
            patch.object(proxy, "route", side_effect=selected),
        ):
            frontend = proxy.Proxy(("127.0.0.1", 0), "storage", CONFIG)
            self.addCleanup(frontend.server_close)
            self.addCleanup(frontend.shutdown)
            threading.Thread(target=frontend.serve_forever, daemon=True).start()
            target = "/laboratory-files/folder%20name/a%2Bb.docx?X-Amz-Credential=a%2Fb&X-Amz-Signature=0123&x=one&x=two"
            connection = http.client.HTTPConnection(
                "127.0.0.1", frontend.server_port, timeout=2
            )
            connection.request(
                "GET",
                target,
                headers={
                    "Host": "localhost:23900",
                    "Cookie": "private",
                    "Authorization": "private",
                },
            )
            response = connection.getresponse()
            self.assertEqual((response.status, response.read()), (200, b"bytes"))
            connection.close()
        self.assertEqual(observed, [(target, "localhost:23900", None, None)])

    def test_public_commands_encoded_traversal_and_foreign_authorities_are_refused(
        self,
    ):
        cases = [
            "/command",
            "/CommandService.ashx",
            "/%63ommand",
            "/%2563ommand",
            "/cache/../command",
            "/cache/%2e%2e/command",
            "//other/command",
            "/cache/%252fcommand",
            "/ConvertService.ashx",
            "/bad%00path",
        ]
        for path in cases:
            with self.subTest(path=path), self.assertRaises(ValueError):
                proxy.route(CONFIG, "public", "GET", path, "localhost:29843")
        with self.assertRaises(ValueError):
            proxy.route(CONFIG, "public", "GET", "/healthcheck", "other:29843")
        self.assertEqual(
            proxy.route(
                CONFIG,
                "public",
                "GET",
                "/web-apps/apps/api/documents/api.js",
                "localhost:29843",
            ),
            ("https", "onlyoffice", 443),
        )

    def test_gateway_has_only_selected_read_and_callback_routes(self):
        accepted = [
            (
                "gateway",
                "GET",
                "/laboratory-files/object?signature=x",
                "localhost:23900",
                ("http", "garage", 3900),
            ),
            (
                "gateway",
                "POST",
                proxy.CALLBACK + "a" * 64,
                "onlyoffice-gateway:7443",
                ("http", "odoo", 8069),
            ),
            (
                "internal",
                "POST",
                "/ConvertService.ashx",
                "onlyoffice-gateway:9443",
                ("https", "onlyoffice", 443),
            ),
        ]
        for kind, method, path, host, result in accepted:
            self.assertEqual(proxy.route(CONFIG, kind, method, path, host), result)
        for kind, method, path, host in [
            ("gateway", "GET", "/web/login", "onlyoffice-gateway:7443"),
            ("gateway", "GET", proxy.CALLBACK + "a" * 64, "onlyoffice-gateway:7443"),
            ("gateway", "POST", "/laboratory-files/object", "localhost:23900"),
            ("gateway", "GET", "/other-bucket/object", "localhost:23900"),
            ("internal", "GET", "/command", "onlyoffice-gateway:9443"),
            ("internal", "GET", "/web/login", "onlyoffice-gateway:9443"),
        ]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                proxy.route(CONFIG, kind, method, path, host)

    def test_forwarded_origin_is_fixed_and_duplicate_host_or_chunking_is_refused(self):
        from email.message import Message

        headers = Message()
        headers["Host"] = "localhost:29843"
        headers["X-Forwarded-Host"] = "attacker.invalid"
        headers["X-Forwarded-Proto"] = "https"
        headers["Cloudfront-Forwarded-Proto"] = "https"
        forwarded = proxy.headers_for(headers, CONFIG, "public")
        self.assertEqual(forwarded["X-Forwarded-Host"], "localhost:29843")
        self.assertEqual(forwarded["X-Forwarded-Proto"], "http")
        self.assertNotIn("Cloudfront-Forwarded-Proto", forwarded)
        headers["Host"] = "attacker.invalid"
        with self.assertRaises(ValueError):
            proxy.headers_for(headers, CONFIG, "public")
        del headers["Host"]
        headers["Host"] = "localhost:29843"
        headers["Transfer-Encoding"] = "chunked"
        with self.assertRaises(ValueError):
            proxy.headers_for(headers, CONFIG, "public")

    def test_unsafe_redirects_return_502_instead_of_a_browser_navigation(self):
        location = ["/welcome/"]

        class Backend(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", location[0])
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *_args):
                return

        backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        self.addCleanup(backend.server_close)
        self.addCleanup(backend.shutdown)
        threading.Thread(target=backend.serve_forever, daemon=True).start()
        original = proxy.route

        def selected(config, kind, method, raw, host):
            original(config, kind, method, raw, host)
            return "http", "127.0.0.1", backend.server_port

        with (
            patch.object(
                proxy.ssl,
                "create_default_context",
                return_value=ssl.create_default_context(),
            ),
            patch.object(proxy, "route", side_effect=selected),
        ):
            frontend = proxy.Proxy(("127.0.0.1", 0), "public", CONFIG)
            self.addCleanup(frontend.server_close)
            self.addCleanup(frontend.shutdown)
            threading.Thread(target=frontend.serve_forever, daemon=True).start()
            for value in (
                "/\\evil",
                "/%5c%5cevil",
                "//evil",
                "http://evil/",
                "/%2f%2fevil",
                "/%2563ommand",
                "/welcome/",
            ):
                location[0] = value
                connection = http.client.HTTPConnection(
                    "127.0.0.1", frontend.server_port, timeout=2
                )
                connection.request("GET", "/", headers={"Host": "localhost:29843"})
                response = connection.getresponse()
                with self.subTest(location=value):
                    self.assertEqual(
                        response.status, 302 if value == "/welcome/" else 502
                    )
                    if value == "/welcome/":
                        self.assertEqual(
                            response.getheader("Location"),
                            CONFIG["public_origin"] + value,
                        )
                response.read()
                connection.close()

    def test_websocket_response_requires_complete_and_unambiguous_negotiation(self):
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        accept = base64.b64encode(
            hashlib.sha1(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode(),
                usedforsecurity=False,
            ).digest()
        ).decode()
        fields = [
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Accept: {accept}",
        ]

        def head(values):
            return (
                "HTTP/1.1 101 Switching Protocols\r\n" + "\r\n".join(values)
            ).encode()

        self.assertIsNone(proxy.websocket_response(head(fields), key, {}))
        for values in (
            fields[1:],
            [fields[0], fields[2]],
            [*fields, fields[2]],
            [*fields, "Sec-WebSocket-Protocol: unrequested"],
            [*fields, "Sec-WebSocket-Extensions: unrequested"],
            ["Upgrade: other", *fields[1:]],
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                proxy.websocket_response(head(values), key, {})
        self.assertIsNone(
            proxy.websocket_response(
                head([*fields, "Sec-WebSocket-Protocol: chat"]),
                key,
                {"Sec-WebSocket-Protocol": "chat, other"},
            )
        )


if __name__ == "__main__":
    unittest.main()
