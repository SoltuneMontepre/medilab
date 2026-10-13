"""Bounded JSON-RPC over an owned stdio subprocess."""

import json
import queue
import subprocess
import threading
from pathlib import Path

MAX_MESSAGE_BYTES = 64 * 1024 * 1024


def read_message(stream) -> dict | None:
    headers = {}
    while True:
        line = stream.readline()
        if not line:
            if not headers:
                return None
            raise EOFError("Truncated JSON-RPC headers.")
        if line in {b"\r\n", b"\n"}:
            break
        key, value = line.decode("ascii").split(":", 1)
        headers[key.lower()] = value.strip()
    if "content-length" not in headers:
        raise ValueError("Missing JSON-RPC Content-Length.")
    length = int(headers["content-length"])
    if not 0 <= length <= MAX_MESSAGE_BYTES:
        raise ValueError("Invalid JSON-RPC message length.")
    payload = stream.read(length)
    if len(payload) != length:
        raise EOFError("Truncated JSON-RPC payload.")
    message = json.loads(payload)
    if not isinstance(message, dict):
        raise ValueError("JSON-RPC message must be an object.")
    return message


def write_message(stream, message: dict) -> None:
    payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
    stream.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii") + payload)
    stream.flush()


class JsonRpcProcess:
    def __init__(self, command: list[str], cwd: Path, log_path: Path, notification):
        self.notification = notification
        self.pending = {}
        self.counter = 0
        self.state_lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.failure = None
        self.log = log_path.open("wb")
        try:
            self.process = subprocess.Popen(
                command, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log
            )
        except BaseException:
            self.log.close()
            raise
        self.reader = threading.Thread(target=self._read, name="odools-rpc", daemon=True)
        self.reader.start()

    def send(self, message: dict) -> None:
        with self.write_lock:
            if self.process.poll() is not None:
                raise RuntimeError("OdooLS connection closed; inspect the session logs.")
            write_message(self.process.stdin, {"jsonrpc": "2.0", **message})

    def notify(self, method: str, params: dict) -> None:
        self.send({"method": method, "params": params})

    def request(self, method: str, params: dict | None, timeout: float = 120) -> object:
        response_queue = queue.Queue(maxsize=1)
        with self.state_lock:
            if self.failure:
                raise RuntimeError(self.failure)
            self.counter += 1
            request_id = self.counter
            self.pending[request_id] = response_queue
        try:
            self.send({"id": request_id, "method": method, "params": params})
            try:
                response = response_queue.get(timeout=timeout)
            except queue.Empty as exc:
                raise TimeoutError(f"OdooLS timed out during {method} after {timeout}s.") from exc
            if "error" in response:
                raise RuntimeError(f"OdooLS {method}: {response['error']}")
            return response.get("result")
        finally:
            with self.state_lock:
                self.pending.pop(request_id, None)

    def _read(self) -> None:
        try:
            while (message := read_message(self.process.stdout)) is not None:
                if "method" in message:
                    if "id" in message:
                        self._answer(message)
                    else:
                        self.notification(message["method"], message.get("params"))
                else:
                    with self.state_lock:
                        waiting = self.pending.get(message.get("id"))
                        if waiting:
                            waiting.put_nowait(message)
        except Exception as exc:
            self.failure = f"OdooLS connection closed: {exc}"
        finally:
            with self.state_lock:
                self.failure = self.failure or "OdooLS connection closed; inspect the session logs."
                for waiting in self.pending.values():
                    if waiting.empty():
                        waiting.put_nowait({"error": self.failure})

    def _answer(self, message: dict) -> None:
        method = message["method"]
        if method == "workspace/configuration":
            result = [{"selectedProfile": "default"} for _ in message.get("params", {}).get("items", [])]
        elif method in {
            "client/registerCapability",
            "client/unregisterCapability",
            "window/workDoneProgress/create",
            "window/showMessageRequest",
        }:
            result = None
        else:
            self.send(
                {"id": message["id"], "error": {"code": -32601, "message": f"Unsupported client method: {method}"}}
            )
            return
        self.send({"id": message["id"], "result": result})

    def close(self) -> None:
        if self.process.poll() is None:
            try:
                self.request("shutdown", None, timeout=2)
                self.notify("exit", {})
                self.process.wait(timeout=2)
            except (RuntimeError, OSError, TimeoutError, subprocess.TimeoutExpired):
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
        self.reader.join(timeout=2)
        for pipe in [self.process.stdin, self.process.stdout]:
            if pipe:
                pipe.close()
        self.log.close()
