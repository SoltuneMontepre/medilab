"""Assert genuine Odoo navigation through the public MCP boundary."""

import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .workspace import utf16_position

CASES = json.loads(Path(__file__).with_name("navigation_cases.json").read_text())


async def check_navigation(root: Path) -> dict:
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "odoo_intelligence.cli", "mcp", "--root", str(root)], cwd=str(root)
    )
    async with (
        stdio_client(parameters) as (read, write),
        ClientSession(read, write, read_timeout_seconds=timedelta(seconds=660)) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        assert len(tools.tools) == 7
        report = {"workspace": str(root), "definitions": []}

        async def call(name, arguments):
            result = await session.call_tool(name, arguments)
            if result.isError:
                raise RuntimeError(f"{name}: {result.content}")
            return result.structuredContent or json.loads(
                next(item.text for item in result.content if item.type == "text")
            )

        for case in CASES:
            position = utf16_position((root / case["path"]).read_text(), case["needle"], case["offset"])
            arguments = {"path": case["path"], **position}
            result = await call("definition", arguments)
            targets = result["result"] or []
            assert any((item.get("targetUri") or item.get("uri")).endswith(case["target"]) for item in targets), result
            assert result["workspace"] == str(root)
            report["definitions"].append({"name": case["name"], "arguments": arguments, "targets": targets})
        field = report["definitions"][2]["arguments"]
        completion = (await call("completion", field))["result"]
        items = completion.get("items", []) if isinstance(completion, dict) else completion
        assert any(item["label"] == "main_group_id" for item in items), completion
        report["completion"] = {"expected_label": "main_group_id", "item_count": len(items)}
        report["hover"] = (await call("hover", field))["result"]
        assert "ParameterGroup" in json.dumps(report["hover"]), report["hover"]
        references = await call("references", {**report["definitions"][1]["arguments"], "include_declaration": True})
        assert references["result"], references
        report["references"] = references["result"]
        symbols = (await call("document_symbols", {"path": field["path"]}))["result"]
        assert any(item["name"] == "TestParameter" for item in symbols), symbols
        report["document_symbols"] = [item["name"] for item in symbols]
        report["diagnostics"] = await call("diagnostics", {"path": field["path"]})
        unsafe = await session.call_tool("definition", {"path": "../outside.py", "line": 0, "character": 0})
        assert unsafe.isError
        report["path_escape_rejected"] = True
        report["status"] = await call("status", {})
        return report


def verify(root: Path) -> None:
    report = asyncio.run(check_navigation(root))
    destination = root / ".local" / "verification" / "mcp-navigation.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Odoo MCP navigation checks passed: {destination}")
