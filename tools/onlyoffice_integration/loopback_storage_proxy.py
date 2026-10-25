"""Expose the owned Garage fixture at Document Server's loopback presigned origin without logging requests."""

import http.client
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

BUCKET = re.compile(r"laboratory-files(?:-[a-z0-9-]{1,63})?")


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
        decoded = unquote(segment, errors="strict")
        if decoded in (".", "..") or any(char in "/\\" or ord(char) < 32 or ord(char) == 127 for char in decoded):
            raise ValueError("Invalid fixture object path")
    return parts.path + ("?" + parts.query if parts.query else "")


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
        connection = http.client.HTTPConnection("garage", 3900, timeout=30)
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


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 3900), Handler).serve_forever()
