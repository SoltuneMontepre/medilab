"""Private test relay: fault injection and redacted evidence around unchanged callback HTTP requests."""

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import jwt
import requests

from .editing_service import SECRET
from odoo.addons.sol_laboratory.constants.laboratory_editing import CALLBACK_PREFIX, JWT_HEADER
from odoo.addons.sol_laboratory.services.onlyoffice_jwt import EditingCallbackRefused, sign, verify_callback

PLUGIN_GUID = "asc.{6F817117-1710-4E04-8031-171000000004}"


class OnlyofficeRealRelay:
    def __init__(self, case, document_server, marker, extension):
        self.case = case
        self.document_server = document_server
        self.marker = marker
        self.extension = extension
        self.config = {}
        self.events = []
        self.deliveries = []
        self.lock = threading.RLock()
        self.edited = False
        self.edited_participants = set()
        self.failures = 0
        self.negative_control = False
        self.unavailable = False
        self.on_final = None
        self.parallel_copies = 1
        self.forward_timeout = 90
        relay = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def answer(self, status, body, content_type="application/json"):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", document_server)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                result = relay.asset(self.path)
                if result is None:
                    self.answer(404, b"{}")
                else:
                    body, content_type = result
                    self.answer(200, body, content_type)

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                if urlsplit(self.path).path == "/edited":
                    relay.edited = True
                    relay.edited_participants.add(parse_qs(urlsplit(self.path).query).get("participant", ["0"])[0])
                    self.answer(200, b"{}")
                    return
                if self.path != CALLBACK_PREFIX + case.callback_token:
                    self.answer(404, b"{}")
                    return
                status, answer = relay.deliver(body, dict(self.headers))
                self.answer(status, answer)

        self.server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        self.url = f"http://runner:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        case.addCleanup(self.server.server_close)
        case.addCleanup(self.server.shutdown)

    def asset(self, path):
        parts = urlsplit(path)
        participant = parse_qs(parts.query).get("participant", ["0"])[0]
        path = parts.path
        if path == "/editor":
            values = deepcopy(self.config)
            values.pop("token")
            if participant != "0":
                values["editorConfig"]["user"] = {"id": "agent4-user-" + participant, "name": (self.marker * 6)[:255]}
            values["editorConfig"]["plugins"]["pluginsData"] = [
                self.url + "/plugin/config.json?participant=" + participant
            ]
            configuration = json.dumps({**values, "token": sign(values, SECRET, 900)}).replace("<", "\\u003c")
            page = f"""<!doctype html><html><body style="margin:0"><div id="editor"></div>
<script src="{self.document_server}/web-apps/apps/api/documents/api.js"></script><script>
window.dirty = false; window.sawDirty = false;
const config = {configuration};
config.width = '100%'; config.height = '100vh';
config.events = {{onDocumentStateChange: function(e) {{
  window.dirty = e.data; window.sawDirty = window.sawDirty || e.data;
}}}};
window.editor = new DocsAPI.DocEditor('editor', config);
</script></body></html>"""
            return page.encode(), "text/html"
        if path == "/state":
            return json.dumps({"edited": participant in self.edited_participants}).encode(), "application/json"
        if path == "/plugin/config.json":
            return json.dumps(
                {
                    "name": "Integration edit",
                    "guid": PLUGIN_GUID,
                    "baseUrl": "",
                    "variations": [
                        {
                            "description": "Integration edit",
                            "url": "index.html?participant=" + participant,
                            "icons": [],
                            "isViewer": False,
                            "EditorsSupport": ["word", "cell", "slide"],
                            "isVisual": False,
                            "isModal": False,
                            "isInsideMode": False,
                            "initDataType": "none",
                            "initData": "",
                            "buttons": [],
                        }
                    ],
                }
            ).encode(), "application/json"
        if path == "/plugin/index.html":
            return (
                f'<script src="{self.document_server}/sdkjs-plugins/v1/plugins.js"></script>'
                f'<script src="code.js?participant={participant}"></script>'
            ).encode(), "text/html"
        if path == "/plugin/code.js":
            return self.plugin_code(participant).encode(), "application/javascript"
        return None

    def plugin_code(self, participant="0"):
        return (
            """window.Asc.plugin.init = function() {
  Asc.scope.marker = MARKER;
  Asc.scope.extension = EXTENSION;
  this.callCommand(function() {
    var marker = Asc.scope.marker;
    if (Asc.scope.extension === 'docx') {
      var paragraph = Api.CreateParagraph(); paragraph.AddText(marker);
      Api.GetDocument().InsertContent([paragraph]);
    } else if (Asc.scope.extension === 'xlsx') {
      Api.GetActiveSheet().GetRange('A1').SetValue(marker);
    } else {
      var slide = Api.GetPresentation().GetSlideByIndex(0);
      var shape = Api.CreateShape('rect', 8000000, 1000000,
          Api.CreateNoFill(), Api.CreateStroke(0, Api.CreateNoFill()));
      var paragraph = Api.CreateParagraph(); paragraph.AddText(marker);
      shape.GetDocContent().Push(paragraph); slide.AddObject(shape);
    }
    return true;
  }, false, true, function(result) {
    if (result === true) fetch('../edited?participant=' + PARTICIPANT, {method: 'POST'});
  });
};""".replace("MARKER", json.dumps(self.marker))
            .replace("EXTENSION", json.dumps(self.extension))
            .replace("PARTICIPANT", json.dumps(participant))
        )

    def deliver(self, body, headers):
        headers = requests.structures.CaseInsensitiveDict(headers)
        fields = json.loads(body)
        final = fields.get("status") == 2
        event = {
            "at": time.time(),
            "status": fields.get("status"),
            "bytes": len(body),
            "header_bytes": len(headers.get(JWT_HEADER, "").encode()),
            "body_token_bytes": len(fields.get("token", "").encode()),
            "users_count": len(fields.get("users", [])),
            "history_json_bytes": len(json.dumps(fields.get("history", {})).encode()),
        }
        tokens = {"body": fields.get("token"), "header": headers.get(JWT_HEADER, "").removeprefix("Bearer ")}
        for name, token in tokens.items():
            if token:
                event[name + "_sha256"] = hashlib.sha256(token.encode()).hexdigest()
                claims = jwt.decode(token, SECRET, algorithms=["HS256"])
                event[name + "_iat"] = claims.get("iat")
                event[name + "_exp"] = claims.get("exp")
        try:
            verify_callback(fields, headers.get(JWT_HEADER), SECRET)
            event["jwt_consistent"] = True
        except EditingCallbackRefused:
            event["jwt_consistent"] = False
        with self.lock:
            self.deliveries.append((body, headers))
            self.events.append(event)
            if final and self.on_final:
                self.on_final()
            if final and self.negative_control:
                event["http"] = 200
                event["error"] = 1
                return 200, b'{"error":1}'
            if final and self.failures:
                self.failures -= 1
                event["http"] = 503
                event["error"] = 1
                return 503, b'{"error":1}'
            if final and self.unavailable:
                event["http"] = 503
                event["error"] = 1
                return 503, b'{"error":1}'

        def forward():
            return requests.post(
                self.case.http_url + CALLBACK_PREFIX + self.case.callback_token,
                data=body,
                headers={"Content-Type": "application/json", JWT_HEADER: headers.get(JWT_HEADER, "")},
                timeout=self.forward_timeout,
                allow_redirects=False,
            )

        try:
            if final and self.parallel_copies > 1:
                with ThreadPoolExecutor(max_workers=self.parallel_copies) as pool:
                    responses = list(pool.map(lambda _index: forward(), range(self.parallel_copies)))
                event["parallel_http"] = [response.status_code for response in responses]
                response = responses[0]
            else:
                response = forward()
        except requests.RequestException:
            event["http"] = 503
            event["error"] = 1
            return 503, b'{"error":1}'
        event["http"] = response.status_code
        event["error"] = response.json().get("error")
        return response.status_code, response.content

    def final_events(self):
        with self.lock:
            return [dict(event) for event in self.events if event["status"] == 2 and "http" in event]
