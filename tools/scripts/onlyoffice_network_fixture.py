"""Synthetic network protocol endpoints and actual-proxy TLS/WebSocket controls."""

import base64
import hashlib
import os
import socket
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

IMAGE = "docker.io/library/python:3.12.13-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36"
LABEL = "com.medilab.onlyoffice.network-proof"
BACKEND = r"""
import json,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_GET(self):
  data=b'owned-docker-proof';self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def do_POST(self):
  data=b'{"error":1}';self.send_response(403);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
for port in (3900,3903,5432,8069,8978):
 server=ThreadingHTTPServer(('0.0.0.0',port),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
threading.Event().wait()
"""
DS = r"""
import base64,hashlib,ssl
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def log_message(self,*args): pass
 def do_GET(self):
  if self.headers.get('Upgrade','').lower()=='websocket':
   key=self.headers['Sec-WebSocket-Key'];accept=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode();self.send_response(101);self.send_header('Upgrade','websocket');self.send_header('Connection','Upgrade');self.send_header('Sec-WebSocket-Accept',accept);self.end_headers()
   for _ in range(2):
    head=self.rfile.read(2);length=head[1]&127;mask=self.rfile.read(4);data=self.rfile.read(length);decoded=bytes(value^mask[index%4] for index,value in enumerate(data));self.wfile.write(bytes([129,len(decoded)])+decoded);self.wfile.flush()
   return
  data=b'true' if self.path=='/healthcheck' else b'owned-docker-proof';self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
class Server(ThreadingHTTPServer):
 def get_request(self):
  stream,address=self.socket.accept();context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain('/run/onlyoffice-tls/tls.crt','/run/onlyoffice-tls/tls.key')
  try:return context.wrap_socket(stream,server_side=True),address
  except OSError:stream.close();raise
Server(('0.0.0.0',443),Handler).serve_forever()
"""
GATEWAY = "from proxy import main;main()"
BASELINE_PUBLIC = "import json;from pathlib import Path;from proxy import Proxy;Proxy(('0.0.0.0',8080),'public',json.loads(Path('/run/onlyoffice-config/runtime.json').read_text())).serve_forever()"
PROBE = r"""
import json,socket,sys
result=[]
for host,port in json.loads(sys.argv[1]):
 try:
  s=socket.create_connection((host,port),timeout=1);s.close();result.append(True)
 except OSError:result.append(False)
print(json.dumps(result))
"""


def host_get(port, path="/healthcheck", authority=None):
    try:
        with build_opener(ProxyHandler({})).open(
            Request(
                f"http://localhost:{port}" + path,
                headers={"Host": authority} if authority else {},
            ),
            timeout=2,
        ) as response:
            return response.status, response.read(1024)
    except HTTPError as error:
        return error.code, error.read(1024)
    except OSError:
        return None


def certificate_variant(directory, trusted, hostname):
    from datetime import UTC, datetime, timedelta

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    original = x509.load_pem_x509_certificate(
        (directory / "tls/server/tls.crt").read_bytes()
    )
    signer = (
        serialization.load_pem_private_key(
            (directory / "tls/ca.key").read_bytes(), password=None
        )
        if trusted
        else rsa.generate_private_key(public_exponent=65537, key_size=2048)
    )
    issuer = (
        original.issuer
        if trusted
        else x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "Untrusted synthetic CA")]
        )
    )
    now = datetime.now(UTC)
    return (
        x509.CertificateBuilder()
        .subject_name(original.subject)
        .issuer_name(issuer)
        .public_key(original.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .sign(signer, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM)
    )


def websocket(port, marker):
    def receive(stream, length):
        data = b""
        while len(data) < length:
            part = stream.recv(length - len(data))
            if not part:
                raise RuntimeError(
                    "The actual proxy WebSocket closed before its duplex control completed"
                )
            data += part
        return data

    key = base64.b64encode(os.urandom(16)).decode()
    with socket.create_connection(("127.0.0.1", port), timeout=5) as stream:
        stream.sendall(
            (
                f"GET /doc/synthetic/c HTTP/1.1\r\nHost: localhost:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {key}\r\n\r\n"
            ).encode()
        )
        head = b""
        while not head.endswith(b"\r\n\r\n") and len(head) < 16384:
            head += receive(stream, 1)
        expected = base64.b64encode(
            hashlib.sha1(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode(),
                usedforsecurity=False,
            ).digest()
        )
        if not head.startswith(b"HTTP/1.1 101") or expected not in head:
            raise RuntimeError(
                "The actual public proxy did not validate its WebSocket upgrade"
            )
        for suffix in ("first", "second"):
            payload = (marker + suffix).encode()
            mask = os.urandom(4)
            stream.sendall(
                bytes([129, 128 | len(payload)])
                + mask
                + bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
            )
            if (
                receive(stream, 2) != bytes([129, len(payload)])
                or receive(stream, len(payload)) != payload
            ):
                raise RuntimeError(
                    "The actual WebSocket proxy failed its bidirectional echo"
                )
