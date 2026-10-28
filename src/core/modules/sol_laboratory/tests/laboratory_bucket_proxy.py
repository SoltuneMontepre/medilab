import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests


class LaboratoryBucketProxy:
    """A local proxy to the real test Garage bucket; selected requests may fail without stopping a shared service."""

    def __init__(self, case, address):
        self.failure = 0
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def forward(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                if proxy.failure:
                    data = b"<Error><Code>AccessDenied</Code></Error>" if proxy.failure == 403 else b""
                    self.send_response(proxy.failure)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                response = requests.request(
                    self.command, address + self.path, data=body, headers=dict(self.headers), timeout=30
                )
                self.send_response(response.status_code)
                for name, value in response.headers.items():
                    if name.lower() not in ("connection", "transfer-encoding", "content-length", "content-encoding"):
                        self.send_header(name, value)
                self.send_header("Content-Length", str(len(response.content)))
                self.end_headers()
                self.wfile.write(response.content)

            do_GET = do_HEAD = do_POST = do_PUT = do_DELETE = forward

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        case.addCleanup(self.server.server_close)
        case.addCleanup(self.server.shutdown)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"
