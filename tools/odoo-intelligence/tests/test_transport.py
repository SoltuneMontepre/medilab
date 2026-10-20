import io
import sys
from pathlib import Path

import pytest

from odoo_intelligence.transport import JsonRpcProcess, read_message, write_message


def test_framing_uses_utf8_byte_lengths():
    stream = io.BytesIO()
    message = {"jsonrpc": "2.0", "id": 7, "result": "😀 tiếng Việt"}
    write_message(stream, message)
    stream.seek(0)
    assert read_message(stream) == message


def test_truncated_payload_and_missing_length_fail():
    for data in [b"Content-Length: 40\r\n\r\n{}", b"X-Header: yes\r\n\r\n{}"]:
        stream = io.BytesIO(data)
        with pytest.raises((ValueError, EOFError)):
            read_message(stream)


def test_request_errors_timeout_and_process_cleanup(tmp_path):
    command = [sys.executable, str(Path(__file__).with_name("rpc_server.py"))]
    process = JsonRpcProcess(command, tmp_path, tmp_path / "stderr.log", lambda *_: None)
    try:
        assert process.request("echo", {"text": "MediLab"}) == {"text": "MediLab"}
        with pytest.raises(RuntimeError, match="rejected"):
            process.request("reject", {})
        with pytest.raises(TimeoutError):
            process.request("hang", {}, timeout=0.05)
    finally:
        process.close()
    assert process.process.poll() is not None


def test_dead_process_fails_pending_request_promptly(tmp_path):
    command = [sys.executable, str(Path(__file__).with_name("rpc_server.py"))]
    process = JsonRpcProcess(command, tmp_path, tmp_path / "stderr.log", lambda *_: None)
    try:
        with pytest.raises(RuntimeError, match="closed"):
            process.request("die", {}, timeout=2)
    finally:
        process.close()
