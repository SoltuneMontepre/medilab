"""Expose the owned Garage fixture at Document Server's loopback presigned origin without logging requests."""

import http.client
import os
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
        decoded = segment
        for depth in range(8):
            if decoded in (".", "..") or any(char in "/\\" or ord(char) < 32 or ord(char) == 127 for char in decoded):
                raise ValueError("Invalid fixture object path")
            if "%" not in decoded:
                break
            if re.search(r"%(?![0-9a-fA-F]{2})", decoded):
                if depth == 0:
                    raise ValueError("Invalid path encoding")
                break
            decoded = unquote(decoded, errors="strict")
        else:
            raise ValueError("Excessively encoded path")
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


def main():
    if os.environ.get("MEDILAB_ONLYOFFICE_STORAGE_FIXTURE") != "isolated-owned":
        raise RuntimeError("Enable only in an explicitly owned isolated fixture.")
    if not os.path.exists("/run/.containerenv") and not os.path.exists("/.dockerenv"):
        raise RuntimeError("The storage adapter requires an owned container network namespace.")
    ThreadingHTTPServer(("127.0.0.1", 3900), Handler).serve_forever()


if __name__ == "__main__":
    main()
