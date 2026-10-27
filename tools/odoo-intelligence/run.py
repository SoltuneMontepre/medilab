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
CLAUDE_CODE = "--client=claude-code"
CODEX = "--client=codex"
COMMANDS = {
    "mcp": ["mcp"],
    "serena-claude-code": [*SERENA, "--context", "claude-code"],
    "serena-ide": [*SERENA, "--context", "ide"],
    "hook-serena-activate": ["serena-hooks", "activate", CLAUDE_CODE],
    "hook-serena-remind": ["serena-hooks", "remind", CLAUDE_CODE],
    "hook-serena-auto-approve": ["serena-hooks", "auto-approve", CLAUDE_CODE],
    "hook-serena-cleanup": ["serena-hooks", "cleanup", CLAUDE_CODE],
    "hook-serena-codex-activate": ["serena-hooks", "activate", CODEX],
    "hook-serena-codex-remind": ["serena-hooks", "remind", CODEX],
    "hook-serena-codex-reset": ["serena-hooks", "reset", CODEX],
    "hook-serena-codex-cleanup": ["serena-hooks", "cleanup", CODEX],
}
GIT_MESSAGE_HOOKS = {"hook-git-message": [], "hook-git-message-codex": [CODEX]}

project = Path(__file__).resolve().parent
mode = sys.argv[1] if len(sys.argv) == 2 else None
if mode in GIT_MESSAGE_HOOKS:
    script = str(project.parents[1] / ".claude/hooks/check_git_message.py")
    raise SystemExit(subprocess.call([sys.executable, script, *GIT_MESSAGE_HOOKS[mode]]))
uv = shutil.which("uv")
if uv is None:
    raise SystemExit("uv not found. Install https://docs.astral.sh/uv/ and run task ai:setup.")
arguments = COMMANDS.get(mode)
if arguments is None:
    raise SystemExit(f"run.py takes one of: {', '.join([*COMMANDS, *GIT_MESSAGE_HOOKS])}.")
command = [uv, "run", "--locked", "--project", str(project), "medilab-odoo", *arguments]
# On Windows os.execv starts a separate process and exits, which closes the client's stdio pipes.
if os.name == "nt":
    raise SystemExit(subprocess.call(command))
os.execv(uv, command)
