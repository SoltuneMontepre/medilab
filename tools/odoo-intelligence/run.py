"""Launch the tooling belonging to this script's worktree, from any working directory."""

import os
import shutil
import sys
from pathlib import Path

# The servers that coding clients start through the launcher, with fixed arguments.
SERENA = [
    "serena",
    "start-mcp-server",
    "--project",
    ".",
    "--enable-web-dashboard",
    "false",
    "--enable-gui-log-window",
    "false",
]
SERVERS = {
    "mcp": ["mcp"],
    "serena-claude-code": [*SERENA, "--context", "claude-code"],
    "serena-ide": [*SERENA, "--context", "ide"],
}

project = Path(__file__).resolve().parent
uv = shutil.which("uv")
if uv is None:
    raise SystemExit("uv not found. Install https://docs.astral.sh/uv/ and run task ai:setup.")
server = SERVERS.get(sys.argv[1]) if len(sys.argv) == 2 else None
if server is None:
    raise SystemExit(f"run.py takes one of: {', '.join(SERVERS)}.")
os.execv(uv, [uv, "run", "--locked", "--project", str(project), "medilab-odoo", *server])
