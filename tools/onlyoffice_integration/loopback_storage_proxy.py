"""Expose the owned Garage fixture at Document Server's loopback presigned origin without logging requests."""

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        connection = http.client.HTTPConnection("garage", 3900, timeout=30)
        try:
            connection.request("GET", self.path, headers={"Host": self.headers["Host"]})
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
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 3900), Handler).serve_forever()
