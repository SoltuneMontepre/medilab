"""Fixed local ONLYOFFICE routes. No request URL, credential or callback payload is logged."""

import base64
import hashlib
import http.client
import json
import os
import re
import select
import socket
import ssl
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

CALLBACK = "/medilab/laboratory-files/callback/"
HOP_HEADERS = {
    "connection",
    "upgrade",
    "keep-alive",
    "proxy-connection",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
}


def safe_path(raw):
    if (
        not isinstance(raw, str)
        or len(raw) > 65536
        or not raw.startswith("/")
        or raw.startswith("//")
        or any(ord(c) < 33 or ord(c) > 126 or c in "\\#" for c in raw)
    ):
        raise ValueError("Invalid request target")
    segments = []
    for item in raw.split("?", 1)[0].split("/"):
        decoded = item
        for depth in range(8):
            if decoded in {".", ".."} or any(
                ord(c) < 32 or ord(c) == 127 or c in "/\\" for c in decoded
            ):
                raise ValueError("Invalid path segment")
            if "%" not in decoded:
                break
            if re.search(r"%(?![0-9A-Fa-f]{2})", decoded):
                if depth == 0:
                    raise ValueError("Invalid path encoding")
                break
            decoded = unquote(decoded, errors="strict")
        else:
            raise ValueError("Excessive path encoding")
        segments.append(decoded.casefold())
    return segments


def public_redirect(location, origin):
    if location.startswith(origin + "/"):
        target = location[len(origin) :]
    elif location.startswith("/") and not location.startswith("//"):
        target = location
    else:
        raise ValueError("Redirect origin refused")
    segments = safe_path(target)
    if any(
        segment in {"command", "commandservice.ashx", "convertservice.ashx"}
        for segment in segments
    ):
        raise ValueError("Redirect route refused")
    return origin + target


def websocket_response(head, key, requested):
    lines = head.decode("latin-1").split("\r\n")
    if not re.fullmatch(r"HTTP/1\.[01] 101(?: .*)?", lines[0]):
        raise ValueError("WebSocket upgrade refused")
    fields = {}
    for line in lines[1:]:
        name, value = line.split(":", 1)
        if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) or any(
            ord(c) < 32 or ord(c) == 127 for c in value
        ):
            raise ValueError("Invalid upgrade header")
        fields.setdefault(name.lower(), []).append(value.strip())
    for name in (
        "upgrade",
        "connection",
        "sec-websocket-accept",
        "sec-websocket-protocol",
        "sec-websocket-extensions",
    ):
        if len(fields.get(name, [])) > 1:
            raise ValueError("Duplicate upgrade header")
    selected = {name: values[0] for name, values in fields.items()}
    expected = base64.b64encode(
        hashlib.sha1(
            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode(),
            usedforsecurity=False,
        ).digest()
    ).decode()
    if (
        selected.get("upgrade", "").lower() != "websocket"
        or "upgrade"
        not in [
            part.strip().lower() for part in selected.get("connection", "").split(",")
        ]
        or selected.get("sec-websocket-accept") != expected
    ):
        raise ValueError("Invalid WebSocket handshake")
    protocols = [
        part.strip()
        for part in requested.get("Sec-WebSocket-Protocol", "").split(",")
        if part.strip()
    ]
    if (
        "sec-websocket-protocol" in selected
        and selected["sec-websocket-protocol"] not in protocols
    ):
        raise ValueError("Unrequested WebSocket protocol")
    extensions = {
        part.strip().split(";", 1)[0].lower()
        for part in requested.get("Sec-WebSocket-Extensions", "").split(",")
        if part.strip()
    }
    if any(
        part.strip().split(";", 1)[0].lower() not in extensions
        for part in selected.get("sec-websocket-extensions", "").split(",")
        if part.strip()
    ):
        raise ValueError("Unrequested WebSocket extension")


def route(config, kind, method, raw, host):
    segments = safe_path(raw)
    pathname = raw.split("?", 1)[0]
    storage = urlsplit(config["storage_origin"]).netloc
    public = urlsplit(config["public_origin"]).netloc
    if kind == "public":
        if (
            host != public
            or method not in {"GET", "HEAD", "POST", "OPTIONS"}
            or any(
                s in {"command", "commandservice.ashx", "convertservice.ashx"}
                for s in segments
            )
        ):
            raise ValueError("Public route refused")
        return "https", "onlyoffice", 443
    if kind in {"storage", "gateway"} and pathname.startswith(f"/{config['bucket']}/"):
        if host != storage or method not in {"GET", "HEAD"}:
            raise ValueError("Storage route refused")
        return (
            ("https", "onlyoffice-gateway", 7443)
            if kind == "storage"
            else ("http", "garage", 3900)
        )
    if kind == "gateway" and pathname.startswith(CALLBACK):
        if (
            method != "POST"
            or host != "onlyoffice-gateway:7443"
            or not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", pathname[len(CALLBACK) :])
        ):
            raise ValueError("Callback route refused")
        return "http", "odoo", 8069
    if (
        kind == "internal"
        and host == "onlyoffice-gateway:9443"
        and (
            (pathname == "/healthcheck" and method in {"GET", "HEAD"})
            or (pathname == "/ConvertService.ashx" and method == "POST")
            or (pathname.startswith("/cache/files/") and method in {"GET", "HEAD"})
        )
    ):
        return "https", "onlyoffice", 443
    raise ValueError("Route refused")


def headers_for(headers, config, kind, *, websocket=False):
    if headers.get_all("Host") is None or len(headers.get_all("Host")) != 1:
        raise ValueError("Invalid authority")
    if headers.get("Transfer-Encoding"):
        raise ValueError("Chunked requests are refused")
    if len(headers.get_all("Content-Length", [])) > 1:
        raise ValueError("Ambiguous request length")
    result = {}
    for key, value in headers.items():
        if (
            key.lower() in HOP_HEADERS
            or key.lower().startswith("x-forwarded-")
            or key.lower() == "cloudfront-forwarded-proto"
        ):
            continue
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Invalid request header")
        if kind == "storage" and key.lower() in {"authorization", "cookie"}:
            continue
        result[key] = value
    if kind == "public":
        result["X-Forwarded-Proto"] = "http"
        result["X-Forwarded-Host"] = urlsplit(config["public_origin"]).netloc
    if websocket:
        result.update({"Connection": "Upgrade", "Upgrade": "websocket"})
    return result


class Proxy(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def handle_error(self, _request, _address):
        print("ONLYOFFICE local proxy request failed.", file=sys.stderr)

    def __init__(self, address, kind, config, tls=False):
        self.kind, self.config = kind, config
        self.client_context = ssl.create_default_context(
            cafile="/run/onlyoffice-ca/ca.crt"
        )
        self.server_context = None
        super().__init__(address, Handler)
        if tls:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(
                "/run/onlyoffice-tls/tls.crt", "/run/onlyoffice-tls/tls.key"
            )
            self.server_context = context

    def get_request(self):
        connection, address = self.socket.accept()
        connection.settimeout(10)
        try:
            if self.server_context:
                connection = self.server_context.wrap_socket(
                    connection, server_side=True
                )
            return connection, address
        except OSError:
            connection.close()
            raise


class IPv6Proxy(Proxy):
    address_family = socket.AF_INET6


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        return

    def do_GET(self):
        self.forward()

    do_HEAD = do_GET
    do_POST = do_GET
    do_OPTIONS = do_GET

    def refuse(self, status):
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

    def forward(self):
        try:
            scheme, host, port = route(
                self.server.config,
                self.server.kind,
                self.command,
                self.path,
                self.headers.get("Host"),
            )
            websocket = self.headers.get("Upgrade", "").lower() == "websocket"
            headers = headers_for(
                self.headers, self.server.config, self.server.kind, websocket=websocket
            )
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0:
                raise ValueError("Request body refused")
            if websocket:
                return self.websocket(host, port, headers, length)
        except (ValueError, UnicodeError):
            self.refuse(400)
            return
        connection = None
        started = False
        try:
            connection = (
                http.client.HTTPSConnection(
                    host, port, timeout=1260, context=self.server.client_context
                )
                if scheme == "https"
                else http.client.HTTPConnection(host, port, timeout=1260)
            )
            connection.putrequest(
                self.command, self.path, skip_host=True, skip_accept_encoding=True
            )
            for key, value in headers.items():
                connection.putheader(key, value)
            connection.endheaders()
            remaining = length
            while remaining:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    raise ConnectionError("Incomplete request")
                connection.send(chunk)
                remaining -= len(chunk)
            answer = connection.getresponse()
            location = answer.getheader("Location")
            redirect = None
            if location:
                if self.server.kind != "public":
                    raise ValueError("Redirect refused")
                redirect = public_redirect(
                    location, self.server.config["public_origin"]
                )
            started = True
            self.send_response(answer.status)
            for key, value in answer.getheaders():
                if key.lower() not in HOP_HEADERS:
                    self.send_header(
                        key, redirect if key.lower() == "location" else value
                    )
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            if self.command != "HEAD":
                while chunk := answer.read(65536):
                    self.wfile.write(chunk)
        except (OSError, ValueError, http.client.HTTPException):
            self.close_connection = True
            if not started:
                self.refuse(502)
        finally:
            if connection:
                connection.close()

    def websocket(self, host, port, headers, length):
        key = self.headers.get("Sec-WebSocket-Key", "")
        if (
            self.server.kind != "public"
            or self.command != "GET"
            or length
            or self.headers.get("Sec-WebSocket-Version") != "13"
            or not re.fullmatch(r"[A-Za-z0-9+/]{22}==", key)
            or "upgrade"
            not in [
                item.strip()
                for item in self.headers.get("Connection", "").lower().split(",")
            ]
        ):
            raise ValueError("Invalid WebSocket handshake")
        upstream = None
        upgraded = False
        try:
            upstream = self.server.client_context.wrap_socket(
                socket.create_connection((host, port), timeout=10), server_hostname=host
            )
            wire = (
                f"GET {self.path} HTTP/1.1\r\n"
                + "".join(f"{name}: {value}\r\n" for name, value in headers.items())
                + "\r\n"
            )
            upstream.sendall(wire.encode("latin-1"))
            response = b""
            while b"\r\n\r\n" not in response and len(response) <= 16384:
                chunk = upstream.recv(4096)
                if not chunk:
                    raise ValueError("Incomplete WebSocket handshake")
                response += chunk
            head, tail = response.split(b"\r\n\r\n", 1)
            websocket_response(head, key, self.headers)
            self.connection.sendall(head + b"\r\n\r\n" + tail)
            upgraded = True
            upstream.settimeout(None)
            self.connection.settimeout(None)
            self.close_connection = True
            while True:
                ready, _, _ = select.select([upstream, self.connection], [], [])
                for source in ready:
                    chunk = source.recv(65536)
                    if not chunk:
                        return
                    (self.connection if source is upstream else upstream).sendall(chunk)
        except (OSError, ValueError):
            if not upgraded:
                self.refuse(502)
        finally:
            if upstream:
                upstream.close()


def main():
    config = json.loads(Path("/run/onlyoffice-config/runtime.json").read_text())
    servers = (
        [
            Proxy(("0.0.0.0", 7443), "gateway", config, True),
            Proxy(("0.0.0.0", 9443), "internal", config, True),
        ]
        if os.environ.get("ONLYOFFICE_PROXY_ROLE") == "gateway"
        else [
            Proxy(("0.0.0.0", config["http_port"]), "public", config),
            Proxy(("127.0.0.1", config["storage_port"]), "storage", config),
        ]
    )
    if os.environ.get("ONLYOFFICE_PROXY_ROLE") != "gateway" and socket.has_ipv6:
        try:
            servers.append(
                IPv6Proxy(("::1", config["storage_port"]), "storage", config)
            )
        except OSError as error:
            import errno

            if error.errno not in {errno.EAFNOSUPPORT, errno.EADDRNOTAVAIL}:
                raise
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Event().wait()


if __name__ == "__main__":
    main()
