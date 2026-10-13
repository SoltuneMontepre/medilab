"""OdooLS lifecycle, indexing and document synchronization."""

import json
import os
import threading
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from .transport import JsonRpcProcess
from .workspace import Workspace

METHOD_CAPABILITIES = {
    "textDocument/definition": "definitionProvider",
    "textDocument/references": "referencesProvider",
    "textDocument/hover": "hoverProvider",
    "textDocument/completion": "completionProvider",
    "textDocument/documentSymbol": "documentSymbolProvider",
}
INDEX_TIMEOUT = 600


class LspClient:
    def __init__(self, root: Path):
        self.workspace = Workspace(root)
        self.transport = None
        self.ready = threading.Event()
        self.interrupted = threading.Event()
        self.lock = threading.RLock()
        self.close_lock = threading.Lock()
        self.capabilities = {}
        self.documents = {}
        self.diagnostics = {}
        self.logs = None
        self.messages = []
        self.addons = {}

    def start(self) -> None:
        with self.lock:
            if self.transport is not None:
                if self.transport.failure:
                    raise RuntimeError(self.transport.failure)
                return
            if not self.workspace.binary.is_file() or not (self.workspace.source / "odoo/release.py").is_file():
                raise RuntimeError("OdooLS or Odoo source is missing; run `task ai:setup` in this worktree.")
            self.logs = self.workspace.session_directory()
            self.interrupted.clear()
            self.addons = self.workspace.addon_snapshot()
            command = [str(self.workspace.binary), "--log-level", "info", "--logs-directory", str(self.logs)]
            self.transport = JsonRpcProcess(command, self.workspace.root, self.logs / "stderr.log", self._notification)
            try:
                result = self.transport.request(
                    "initialize",
                    {
                        "processId": os.getpid(),
                        "rootUri": self.workspace.root.as_uri(),
                        "workspaceFolders": [{"uri": self.workspace.root.as_uri(), "name": self.workspace.root.name}],
                        "capabilities": {
                            "general": {"positionEncodings": ["utf-16"]},
                            "workspace": {
                                "configuration": True,
                                "workspaceFolders": True,
                                "didChangeWatchedFiles": {"dynamicRegistration": True},
                            },
                            "window": {"workDoneProgress": True},
                            "textDocument": {
                                "hover": {"contentFormat": ["markdown", "plaintext"]},
                                "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                                "publishDiagnostics": {"relatedInformation": True, "versionSupport": True},
                            },
                        },
                    },
                )
                self.capabilities = result["capabilities"]
                if self.capabilities.get("positionEncoding", "utf-16") != "utf-16":
                    raise RuntimeError("OdooLS did not negotiate UTF-16 positions.")
                self.transport.notify("initialized", {})
                self.wait_for_index()
            except BaseException:
                self.close()
                raise

    def wait_for_index(self) -> None:
        deadline = time.monotonic() + INDEX_TIMEOUT
        while not self.ready.wait(timeout=0.2):
            transport = self.transport
            if self.interrupted.is_set() or transport is None:
                raise RuntimeError("OdooLS operation was interrupted; start a new query to reinitialize it.")
            if transport.failure:
                raise RuntimeError(transport.failure)
            if time.monotonic() >= deadline:
                raise TimeoutError(f"OdooLS did not finish indexing within {INDEX_TIMEOUT}s; inspect {self.logs}.")

    def _notification(self, method: str, params: object) -> None:
        if method == "$Odoo/loadingStatusUpdate":
            if params == "stop":
                self.ready.set()
            else:
                self.ready.clear()
        elif method == "textDocument/publishDiagnostics":
            self.diagnostics[params["uri"]] = {**params, "received_at": time.time()}
        elif method in {
            "window/logMessage",
            "window/showMessage",
            "$Odoo/invalid_python_path",
            "Odoo/displayCrashNotification",
        }:
            self.messages.append({"method": method, "params": params})
            self.messages = self.messages[-20:]
        if self.logs and method.startswith("$Odoo/"):
            with (self.logs / "notifications.jsonl").open("a", encoding="utf-8") as output:
                output.write(json.dumps({"method": method, "params": params}) + "\n")

    def request(self, method: str, params: dict) -> object:
        if method not in METHOD_CAPABILITIES:
            raise ValueError(f"Unsupported OdooLS method: {method}")
        with self.lock:
            self.start()
            self.wait_for_index()
            if not self.capabilities.get(METHOD_CAPABILITIES[method]):
                raise RuntimeError(f"OdooLS does not advertise {method}.")
            return self.transport.request(method, params)

    def sync_document(self, path: Path) -> str:
        self.start()
        uri = path.as_uri()
        text = path.read_text(encoding="utf-8")
        previous = self.documents.get(uri)
        if previous is None:
            self.transport.notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": uri,
                        "languageId": "xml" if path.suffix == ".xml" else "python",
                        "version": 1,
                        "text": text,
                    }
                },
            )
            self.documents[uri] = {"text": text, "version": 1, "sent_at": time.time()}
        elif previous["text"] != text:
            version = previous["version"] + 1
            self.transport.notify(
                "textDocument/didChange",
                {
                    "textDocument": {"uri": uri, "version": version},
                    "contentChanges": [{"text": text}],
                },
            )
            self.documents[uri] = {"text": text, "version": version, "sent_at": time.time()}
        return uri

    def navigate(
        self, method: str, path: str, line: int | None = None, character: int | None = None, **extra
    ) -> object:
        with self.lock:
            document = self.workspace.document(path)
            position = self.workspace.position(document, line, character) if line is not None else None
            self.start()
            self.refresh_addons()
            params = {"textDocument": {"uri": self.sync_document(document)}, **extra}
            if position is not None:
                params["position"] = position
            if method == "textDocument/references":
                definitions = (
                    self.request(
                        "textDocument/definition",
                        {
                            "textDocument": params["textDocument"],
                            "position": params["position"],
                        },
                    )
                    or []
                )
                if isinstance(definitions, dict):
                    definitions = [definitions]
                # OdooLS 1.6.0 assumes definition text is resident when constructing references.
                for definition in definitions:
                    target_uri = definition.get("targetUri", definition.get("uri"))
                    target = Path(url2pathname(urlparse(target_uri).path))
                    if not target.is_relative_to(self.workspace.root):
                        raise RuntimeError("References to definitions outside this worktree are unsupported.")
                    self.sync_document(target)
                result = self.request(method, params)
                if result and not params.get("context", {}).get("includeDeclaration", False):
                    declarations = {
                        (
                            item.get("targetUri", item.get("uri")),
                            item.get("targetSelectionRange", item.get("range"))["start"]["line"],
                            item.get("targetSelectionRange", item.get("range"))["start"]["character"],
                        )
                        for item in definitions
                    }
                    return [
                        item
                        for item in result
                        if (item["uri"], item["range"]["start"]["line"], item["range"]["start"]["character"])
                        not in declarations
                    ]
                return result
            return self.request(method, params)

    def published_diagnostics(self, path: str) -> dict:
        with self.lock:
            self.start()
            self.refresh_addons()
            uri = self.sync_document(self.workspace.document(path))
            # A supported request flushes preceding document notifications without pull diagnostics.
            self.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}})
            published = self.diagnostics.get(uri)
            if not published:
                return {"status": "unavailable", "diagnostics": None, "reason": "No published diagnostics received."}
            fresh = published["received_at"] >= self.documents[uri]["sent_at"]
            if published.get("version") is not None:
                fresh = fresh and published["version"] == self.documents[uri]["version"]
            return {
                "status": "published" if fresh else "stale",
                **published,
                "document_version": self.documents[uri]["version"],
                "freshness": "Server version is authoritative when provided; timestamps do not prove completeness.",
            }

    def refresh_addons(self) -> None:
        current = self.workspace.addon_snapshot()
        changes = self.workspace.addon_changes(self.addons, current)
        for change in changes:
            if change["type"] == 3 and change["uri"] in self.documents:
                self.transport.notify("textDocument/didClose", {"textDocument": {"uri": change["uri"]}})
                self.documents.pop(change["uri"])
            elif change["type"] == 2 and change["uri"] in self.documents:
                self.sync_document(Path(url2pathname(urlparse(change["uri"]).path)))
        if changes:
            self.transport.notify("workspace/didChangeWatchedFiles", {"changes": changes})
        self.addons = current

    def close(self) -> None:
        with self.close_lock:
            self.interrupted.set()
            if self.transport:
                self.transport.close()
                self.transport = None
            self.ready.clear()
            self.documents.clear()
            self.diagnostics.clear()
