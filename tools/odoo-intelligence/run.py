"""Launch the tooling belonging to this script's worktree, from any working directory."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# The servers and hooks that coding clients start through the launcher, with fixed arguments.
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
COMMANDS = {
    "mcp": ["mcp"],
    "serena-claude-code": [*SERENA, "--context", "claude-code"],
    "serena-ide": [*SERENA, "--context", "ide"],
    "hook-serena-activate": ["serena-hooks", "activate", "--client=claude-code"],
    "hook-serena-remind": ["serena-hooks", "remind", "--client=claude-code"],
    "hook-serena-auto-approve": ["serena-hooks", "auto-approve", "--client=claude-code"],
    "hook-serena-cleanup": ["serena-hooks", "cleanup", "--client=claude-code"],
}
GIT_MESSAGE_HOOK = "hook-git-message"

project = Path(__file__).resolve().parent
mode = sys.argv[1] if len(sys.argv) == 2 else None
if mode == GIT_MESSAGE_HOOK:
    raise SystemExit(subprocess.call([sys.executable, str(project.parents[1] / ".claude/hooks/check_git_message.py")]))
uv = shutil.which("uv")
if uv is None:
    raise SystemExit("uv not found. Install https://docs.astral.sh/uv/ and run task ai:setup.")
arguments = COMMANDS.get(mode)
if arguments is None:
    raise SystemExit(f"run.py takes one of: {', '.join([*COMMANDS, GIT_MESSAGE_HOOK])}.")
command = [uv, "run", "--locked", "--project", str(project), "medilab-odoo", *arguments]
# On Windows os.execv starts a separate process and exits, which closes the client's stdio pipes.
if os.name == "nt":
    raise SystemExit(subprocess.call(command))
os.execv(uv, command)
