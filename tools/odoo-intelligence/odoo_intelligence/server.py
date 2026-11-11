"""Read-only OdooLS tools shared by MCP-capable coding clients."""

from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .lsp import LspClient
from .workspace import RELEASE


def create_server(root: Path) -> MCPServer:
    client = LspClient(root)

    @asynccontextmanager
    async def lifespan(_server):
        try:
            yield
        finally:
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(client.close)

    server = MCPServer(
        "MediLab OdooLS",
        instructions="Use relative worktree paths and zero-based UTF-16 positions. Tools query official OdooLS. "
        "They do not edit code. Serena provides symbol editing. Diagnostics may be unavailable or stale.",
        lifespan=lifespan,
        log_level="WARNING",
    )
    readonly = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)

    async def run(operation, *args, **kwargs):
        try:
            return await anyio.to_thread.run_sync(partial(operation, *args, **kwargs), abandon_on_cancel=True)
        except anyio.get_cancelled_exc_class():
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(client.close)
            raise
        except Exception as error:
            raise ToolError(str(error)) from error

    async def navigate(method, path, line=None, character=None, **extra):
        return {
            "workspace": str(client.workspace.root),
            "server_version": RELEASE["version"],
            "result": await run(client.navigate, method, path, line, character, **extra),
        }

    @server.tool(annotations=readonly)
    async def definition(path: str, line: int, character: int) -> dict:
        """Resolve an Odoo model, field, inherited member or Python/XML symbol at a zero-based UTF-16 position."""
        return await navigate("textDocument/definition", path, line, character)

    @server.tool(annotations=readonly)
    async def references(path: str, line: int, character: int, include_declaration: bool = False) -> dict:
        """Find Odoo-aware references at a zero-based UTF-16 position; results depend on indexed dependencies."""
        return await navigate(
            "textDocument/references", path, line, character, context={"includeDeclaration": include_declaration}
        )

    @server.tool(annotations=readonly)
    async def hover(path: str, line: int, character: int) -> dict:
        """Read Odoo type and member information at a zero-based UTF-16 position."""
        return await navigate("textDocument/hover", path, line, character)

    @server.tool(annotations=readonly)
    async def completion(path: str, line: int, character: int) -> dict:
        """Complete Odoo fields or model names at a zero-based UTF-16 position in the current disk document."""
        return await navigate("textDocument/completion", path, line, character)

    @server.tool(annotations=readonly)
    async def document_symbols(path: str) -> dict:
        """List the Python/XML document symbols reported by OdooLS."""
        return await navigate("textDocument/documentSymbol", path)

    @server.tool(annotations=readonly)
    async def diagnostics(path: str) -> dict:
        """Read pushed diagnostics with freshness metadata; unavailable or stale does not mean error-free."""
        return await run(client.published_diagnostics, path)

    def snapshot():
        client.start()
        return {
            "workspace": str(client.workspace.root),
            "server_version": RELEASE["version"],
            "odoo_revision": RELEASE["odoo_revision"],
            "process_id": client.transport.process.pid,
            "indexing_complete": client.ready.is_set(),
            "capabilities": client.capabilities,
            "logs": str(client.logs),
            "messages": client.messages,
        }

    @server.tool(annotations=readonly)
    async def status() -> dict:
        """Initialize OdooLS and report the actual worktree, indexing state, capabilities and session log path."""
        return await run(snapshot)

    return server
