"""Launch the tooling belonging to this script's worktree, from any working directory."""

import os
import shutil
import sys
from pathlib import Path

# Coding clients start only these servers through the launcher.
SERVERS = {"mcp": "mcp", "serena": "serena"}

project = Path(__file__).resolve().parent
uv = shutil.which("uv")
if uv is None:
    raise SystemExit("uv not found. Install https://docs.astral.sh/uv/ and run task ai:setup.")
server = SERVERS.get(sys.argv[1]) if len(sys.argv) > 1 else None
if server is None:
    raise SystemExit(f"run.py starts one of: {', '.join(SERVERS)}.")
os.execv(uv, [uv, "run", "--locked", "--project", str(project), "medilab-odoo", server, *sys.argv[2:]])
