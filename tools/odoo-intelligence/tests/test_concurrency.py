import asyncio
import json
import os
import subprocess
import sys
from datetime import timedelta

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from odoo_intelligence.workspace import PACKAGE_ROOT, Workspace, utf16_position


def test_mcp_sessions_isolate_git_worktrees_and_refresh_dependencies(tmp_path):
    installed = Workspace(PACKAGE_ROOT.parents[1])
    if not installed.binary.exists():
        pytest.skip("Run task ai:setup for the live worktree test.")
    first = tmp_path / "repository"
    second = tmp_path / "linked-checkout"
    first.mkdir()
    subprocess.run(["git", "init", "--quiet", str(first)], check=True)
    (first / ".gitignore").write_text(".local/\n")
    (first / "odools.toml").write_text((installed.root / "odools.toml").read_text())
    addon = first / "src/core/modules/navigation_probe"
    addon.mkdir(parents=True)
    (addon / "__manifest__.py").write_text('{"name": "Navigation probe", "depends": ["base"]}')
    (addon / "__init__.py").write_text("from . import models, usage\n")
    (addon / "models.py").write_text("""from odoo import fields, models

# Mô hình kiểm tra điều hướng.
class Probe(models.Model):
    _name = "medilab.concurrent.probe"
    # The marker that identifies this checkout.
    marker_first = fields.Char()
""")
    (addon / "usage.py").write_text("""from odoo import models

# Phần mở rộng của mô hình kiểm tra điều hướng.
class ProbeUsage(models.Model):
    _inherit = "medilab.concurrent.probe"

    def read_marker(self):
        return self.marker_first
""")
    subprocess.run(["git", "-C", str(first), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(first),
            "-c",
            "user.name=Navigation test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "[test] Add navigation fixture",
        ],
        check=True,
    )
    subprocess.run(["git", "-C", str(first), "worktree", "add", "--quiet", "--detach", str(second)], check=True)
    for file in ["models.py", "usage.py"]:
        path = second / "src/core/modules/navigation_probe" / file
        path.write_text(path.read_text().replace("marker_first", "marker_second"))
    for root in [first, second]:
        workspace = Workspace(root)
        workspace.release.parent.mkdir(parents=True)
        workspace.release.symlink_to(installed.release, target_is_directory=True)
        workspace.source.symlink_to(installed.source, target_is_directory=True)

    async def run(root, marker, excluded):
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "odoo_intelligence.cli", "mcp", "--root", str(root)], cwd=str(root)
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write, read_timeout_seconds=timedelta(seconds=660)) as session,
        ):
            await session.initialize()

            async def call(name, arguments):
                response = await session.call_tool(name, arguments)
                assert not response.isError, response
                return response.structuredContent or json.loads(response.content[0].text)

            usage = "src/core/modules/navigation_probe/usage.py"
            position = utf16_position((root / usage).read_text(), "self." + marker, offset=7)
            arguments = {"path": usage, **position}
            definition = await call("definition", arguments)
            assert definition["workspace"] == str(root)
            assert definition["result"][0]["targetUri"].startswith(root.as_uri() + "/")
            completion = (await call("completion", arguments))["result"]
            items = completion["items"] if isinstance(completion, dict) else completion
            assert marker in [item["label"] for item in items]
            assert excluded not in [item["label"] for item in items]
            before = await call("hover", arguments)
            assert ": str" in json.dumps(before), before
            model_path = root / "src/core/modules/navigation_probe/models.py"
            await call("document_symbols", {"path": "src/core/modules/navigation_probe/models.py"})
            model_path.write_text(model_path.read_text().replace("fields.Char()", "fields.Integer()"))
            after = await call("hover", arguments)
            assert ": int" in json.dumps(after), after
            return await call("status", {})

    async def both():
        return await asyncio.gather(
            run(first, "marker_first", "marker_second"), run(second, "marker_second", "marker_first")
        )

    reports = asyncio.run(both())
    assert reports[0]["logs"] != reports[1]["logs"]
    assert reports[0]["workspace"] == str(first)
    assert reports[1]["workspace"] == str(second)
    for report in reports:
        with pytest.raises(ProcessLookupError):
            os.kill(report["process_id"], 0)
