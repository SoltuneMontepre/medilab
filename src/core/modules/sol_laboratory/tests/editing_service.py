"""The editing service as tests see it: its secret and addresses in the environment, its health check, the callbacks
ONLYOFFICE Document Server 9.4 sends, and a local HTTP server standing in for it."""

import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import jwt

from odoo.addons.sol_laboratory.constants.laboratory_editing import (
    INTERNAL_URL_VARIABLE,
    JWT_SECRET_VARIABLE,
    PUBLIC_URL_VARIABLE,
)

SECRET = "test-secret-of-the-editing-service-0123456789"
PUBLIC_URL = "https://docs.lab.example"
INTERNAL_URL = "http://onlyoffice"
# The module whose health check opening a file asks.
HEALTH_CHECK = (
    "odoo.addons.sol_laboratory.models.laboratory_files.laboratory_editing_session_callback.is_editing_service_up"
)


def use_editing_service(case, internal_url=INTERNAL_URL, up=True):
    """Give the test the editing service's secret and addresses, with its health check answering up or not, and
    return the mock of the health check."""
    environment = patch.dict(
        os.environ,
        {JWT_SECRET_VARIABLE: SECRET, INTERNAL_URL_VARIABLE: internal_url, PUBLIC_URL_VARIABLE: PUBLIC_URL},
    )
    environment.start()
    case.addCleanup(environment.stop)
    health = patch(HEALTH_CHECK, return_value=up)
    case.addCleanup(health.stop)
    return health.start()


def callback(fields, secret=SECRET, lifetime=300, header=True, body_token=True):
    """The body and the token header of a callback as Document Server 9.4 sends it: the body's fields with a token of
    them, and a header token whose payload is the fields."""
    now = int(time.time())
    times = {"iat": now, "exp": now + lifetime}
    body = dict(fields)
    if body_token:
        body["token"] = jwt.encode({**fields, **times}, secret, algorithm="HS256")
    token = jwt.encode({"payload": fields, **times}, secret, algorithm="HS256") if header else None
    return body, f"Bearer {token}" if token else None


class LocalEditingService:
    """An HTTP server on 127.0.0.1 answering each path with the status, headers and body a test gives it, and
    recording the paths asked."""

    def __init__(self, case):
        self.answers = {}
        self.asked = []
        self.before_get = None
        service = self

        class Handler(BaseHTTPRequestHandler):
            # Chunked answers need HTTP/1.1.
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                service.asked.append(self.path)
                if service.before_get:
                    service.before_get(self.path)
                status, headers, body = service.answers.get(self.path.split("?")[0], (404, {}, b""))
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                if "Content-Length" not in headers and "Transfer-Encoding" not in headers:
                    self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if headers.get("Transfer-Encoding") == "chunked":
                    for start in range(0, len(body), 1024):
                        part = body[start : start + 1024]
                        self.wfile.write(f"{len(part):x}\r\n".encode() + part + b"\r\n")
                    self.wfile.write(b"0\r\n\r\n")
                else:
                    self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        case.addCleanup(self.server.server_close)
        case.addCleanup(self.server.shutdown)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def answer(self, path, body=b"", status=200, headers=None):
        self.answers[path] = (status, headers or {}, body)
