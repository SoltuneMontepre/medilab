"""Expose the owned Garage fixture at Document Server's loopback presigned origin without logging requests."""

import os
import re
import ssl
from http.client import HTTPSConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit

BUCKET = re.compile(r"laboratory-files(?:-[a-z0-9-]{1,63})?")


def validate_segment(segment):
    decoded = segment
    for depth in range(8):
        if decoded in (".", "..") or any(char in "/\\" or ord(char) < 32 or ord(char) == 127 for char in decoded):
            raise ValueError("Invalid fixture object path")
        if "%" not in decoded:
            return
        if re.search(r"%(?![0-9a-fA-F]{2})", decoded):
            if depth == 0:
                raise ValueError("Invalid path encoding")
            return
        decoded = unquote(decoded, errors="strict")
    raise ValueError("Excessively encoded path")


def storage_path(raw):
    if (
        not raw.startswith("/")
        or raw.startswith("//")
        or any(ord(char) < 33 or ord(char) > 126 or char == "\\" for char in raw)
    ):
        raise ValueError("Invalid fixture request target")
    parts = urlsplit(raw)
    if parts.scheme or parts.netloc or parts.fragment:
        raise ValueError("Invalid fixture origin")
    segments = parts.path.split("/")[1:]
    if len(segments) < 2 or not BUCKET.fullmatch(segments[0]):
        raise ValueError("Invalid fixture bucket")
    for segment in segments:
        validate_segment(segment)
    # Encode each URI component separately, then refuse any byte-changing normalization of signed URLs.
    path = "/" + "/".join(quote(unquote(segment, errors="strict"), safe="") for segment in segments)
    query = urlencode(
        parse_qsl(parts.query, keep_blank_values=True, errors="strict"),
        quote_via=quote,
        safe="",
    )
    if path != parts.path or query != parts.query:
        raise ValueError("Noncanonical signed object URL")
    return path + ("?" + query if query else "")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        host = self.headers.get("Host")
        if host not in ("localhost:3900", "127.0.0.1:3900"):
            self.send_error(400)
            return
        try:
            path = storage_path(self.path)
        except ValueError:
            self.send_error(400)
            return
        connection = HTTPSConnection("garage-tls", 3900, timeout=30)
        try:
            connection.request("GET", path, headers={"Host": host})
            upstream = connection.getresponse()
            self.send_response(upstream.status)
            for name, value in upstream.getheaders():
                if name.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(name, value)
            self.end_headers()
            while chunk := upstream.read(65536):
                self.wfile.write(chunk)
        finally:
            connection.close()

    def log_message(self, *_args):
        return


class LoopbackTLSServer(ThreadingHTTPServer):
    def __init__(self, address, handler, context):
        super().__init__(address, handler)
        self.socket = context.wrap_socket(self.socket, server_side=True)


def server_context():
    directory = Path(os.environ.get("ONLYOFFICE_FIXTURE_TLS_DIR", "/run/fixture-tls"))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(directory / "tls.crt", directory / "tls.key")
    return context


def main():
    if os.environ.get("MEDILAB_ONLYOFFICE_STORAGE_FIXTURE") != "isolated-owned":
        raise RuntimeError("Enable only in an explicitly owned isolated fixture.")
    if not os.path.exists("/run/.containerenv") and not os.path.exists("/.dockerenv"):
        raise RuntimeError("The storage adapter requires container runtime markers.")
    LoopbackTLSServer(("127.0.0.1", 3900), Handler, server_context()).serve_forever()


if __name__ == "__main__":
    main()
