import asyncio
import threading
import time

import pytest

from odoo_intelligence import server as server_module
from odoo_intelligence.lsp import LspClient
from odoo_intelligence.server import create_server


def test_mcp_tools_are_read_only_and_do_not_include_rename(tmp_path):
    server = create_server(tmp_path)
    tools = asyncio.run(server.list_tools())
    assert {tool.name for tool in tools} == {
        "definition",
        "references",
        "hover",
        "completion",
        "document_symbols",
        "diagnostics",
        "status",
    }
    assert all(tool.annotations.readOnlyHint for tool in tools)
    assert all(not tool.annotations.destructiveHint for tool in tools)
    definition = next(tool for tool in tools if tool.name == "definition")
    assert set(definition.inputSchema["required"]) == {"path", "line", "character"}


def test_invalid_path_fails_before_missing_server(tmp_path):
    server = create_server(tmp_path)
    try:
        asyncio.run(server.call_tool("definition", {"path": "../outside.py", "line": 0, "character": 0}))
    except Exception as error:
        assert "worktree" in str(error)
    else:
        raise AssertionError("Unsafe navigation path was accepted.")


def test_cancellation_interrupts_an_owned_lsp_wait(tmp_path, monkeypatch):
    released = threading.Event()
    client = LspClient(tmp_path)
    monkeypatch.setattr(server_module, "LspClient", lambda _: client)

    def slow_navigation(*_args, **_kwargs):
        released.wait(timeout=0.5)
        return []

    monkeypatch.setattr(client, "navigate", slow_navigation)
    monkeypatch.setattr(client, "close", released.set)
    server = create_server(tmp_path)

    async def run():
        start = time.monotonic()
        call = server.call_tool("definition", {"path": "unused.py", "line": 0, "character": 0})
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(call, timeout=0.02)
        assert time.monotonic() - start < 0.3
        assert released.is_set()

    asyncio.run(run())


def test_disconnect_stops_the_official_child_during_indexing(tmp_path):
    import json
    import os
    import sys
    from datetime import timedelta

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    from odoo_intelligence.workspace import PACKAGE_ROOT, Workspace

    installed = Workspace(PACKAGE_ROOT.parents[1])
    if not installed.binary.exists():
        pytest.skip("Run task ai:setup for the live disconnect test.")
    workspace = Workspace(tmp_path)
    workspace.release.parent.mkdir(parents=True)
    workspace.release.symlink_to(installed.release, target_is_directory=True)
    workspace.source.symlink_to(installed.source, target_is_directory=True)
    (workspace.local / "logs").mkdir()
    (tmp_path / "odools.toml").write_text((installed.root / "odools.toml").read_text())
    addon = tmp_path / "src/core/modules/navigation_probe"
    addon.mkdir(parents=True)
    (addon / "__manifest__.py").write_text('{"name": "Navigation probe", "depends": ["base"]}')
    (addon / "__init__.py").write_text("")

    async def run():
        previous = set((workspace.local / "logs").iterdir())
        params = StdioServerParameters(
            command=sys.executable, args=[str(PACKAGE_ROOT / "run.py"), "mcp", "--root", str(tmp_path)]
        )
        child_pid = None
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write, read_timeout_seconds=timedelta(seconds=660)) as session,
        ):
            await session.initialize()
            request = asyncio.create_task(session.call_tool("status", {}))
            for _ in range(200):
                await asyncio.sleep(0.05)
                for directory in set((workspace.local / "logs").iterdir()) - previous:
                    notification_file = directory / "notifications.jsonl"
                    if not notification_file.exists():
                        continue
                    for line in notification_file.read_text().splitlines():
                        message = json.loads(line)
                        if message["method"] == "$Odoo/setPid":
                            child_pid = message["params"]["server_pid"]
                if child_pid:
                    break
            assert isinstance(child_pid, int), "Official server did not report its owned process."
            assert not request.done(), "The test must disconnect while indexing is still active."
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
        for _ in range(100):
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                return
            await asyncio.sleep(0.05)
        raise AssertionError("The owned OdooLS child survived MCP disconnect during indexing.")

    asyncio.run(run())
