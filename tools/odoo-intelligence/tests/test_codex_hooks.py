import json
import os
import re
import runpy
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HOOKS = json.loads((ROOT / ".codex/hooks.json").read_text())["hooks"]


def test_codex_hooks_use_the_worktree_launcher_and_supported_events():
    server = tomllib.loads((ROOT / ".codex/config.toml").read_text())["mcp_servers"]["odoo"]
    prefix = [server["command"], *server["args"][:-1]]
    expected = {
        "hook-git-message-codex": ("PreToolUse", "^Bash$", 30),
        "hook-serena-codex-remind": ("PreToolUse", "^Bash$", 30),
        "hook-serena-codex-reset": ("PostToolUse", "^mcp__serena__.*$", 30),
        "hook-serena-codex-activate": ("SessionStart", None, 30),
        "hook-serena-codex-cleanup": ("SessionEnd", None, 3),
    }
    found = {}
    for event, groups in HOOKS.items():
        for group in groups:
            for hook in group["hooks"]:
                arguments = shlex.split(hook["command"])
                assert hook["type"] == "command"
                assert arguments[:-1] == prefix
                assert "$" not in hook["command"]
                found[arguments[-1]] = (event, group.get("matcher"), hook["timeout"])
    assert found == expected
    matcher = HOOKS["PostToolUse"][0]["matcher"]
    assert re.fullmatch(matcher, "mcp__serena__find_symbol")
    assert not re.fullmatch(matcher, "mcp__odoo__definition")


@pytest.mark.parametrize("environment", [True, False])
@pytest.mark.parametrize("operation", ["activate", "remind", "reset", "cleanup"])
def test_codex_launcher_selects_the_codex_client(monkeypatch, operation, environment):
    command = []
    folders = []

    def which(name, path=None):
        if path is None:
            return "uv"
        folders.extend(path.split(os.pathsep))
        return "python" if environment else None

    def capture(*arguments):
        command.extend(arguments[-1])
        raise SystemExit(0)

    monkeypatch.setattr(sys, "argv", ["run.py", f"hook-serena-codex-{operation}"])
    monkeypatch.setattr(shutil, "which", which)
    monkeypatch.setattr(subprocess, "call", capture)
    monkeypatch.setattr(os, "execv", capture)
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(ROOT / "tools/odoo-intelligence/run.py"), run_name="__main__")
    assert stopped.value.code == 0
    environment_folder = ROOT / "tools/odoo-intelligence/.venv"
    assert folders == [str(environment_folder / "Scripts"), str(environment_folder / "bin")]
    if environment:
        launch = ["python", "-P", "-m", "odoo_intelligence.cli"]
    else:
        launch = ["uv", "run", "--locked", "--project", str(ROOT / "tools/odoo-intelligence"), "medilab-odoo"]
    assert command == [*launch, "serena-hooks", operation, "--client=codex"]


def test_launcher_starts_servers_through_the_locked_environment(monkeypatch):
    command = []

    def capture(*arguments):
        command.extend(arguments[-1])
        raise SystemExit(0)

    monkeypatch.setattr(sys, "argv", ["run.py", "mcp"])
    monkeypatch.setattr(shutil, "which", lambda _: "uv")
    monkeypatch.setattr(subprocess, "call", capture)
    monkeypatch.setattr(os, "execv", capture)
    with pytest.raises(SystemExit):
        runpy.run_path(str(ROOT / "tools/odoo-intelligence/run.py"), run_name="__main__")
    assert command[:3] == ["uv", "run", "--locked"]


@pytest.mark.parametrize(
    ("command", "blocked"),
    [
        ("git commit -m 'bad title'", True),
        ("git commit -m '[fix] Correct hook launcher'", False),
        ("gh pr create --title 'bad title'", True),
        ("gh pr edit --title '[docs] Explain hooks'", False),
        ("gh pr create --title '[fix] Correct hooks' --body 'Co-Authored-By: Example'", True),
    ],
)
def test_codex_git_hook_checks_commands_from_a_subdirectory(command, blocked):
    hook = HOOKS["PreToolUse"][0]["hooks"][0]
    arguments = shlex.split(hook["command"])
    payload = {
        "session_id": "test-codex-git-message",
        "hook_event_name": "PreToolUse",
        "cwd": str(ROOT / "src/core"),
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
    result = subprocess.run(
        [sys.executable, *arguments[arguments.index("-c") :]],
        input=json.dumps(payload),
        cwd=ROOT / "src/core",
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    if blocked:
        output = json.loads(result.stdout)["hookSpecificOutput"]
        assert output["hookEventName"] == "PreToolUse"
        assert output["permissionDecision"] == "deny"
        reason = output["permissionDecisionReason"]
        assert "must be '[<type>] <title>'" in reason or "Remove co-author" in reason
    else:
        assert not result.stdout.strip()


@pytest.mark.skipif(os.name != "nt", reason="PowerShell exit-code regression runs on Windows.")
def test_codex_git_hook_denies_through_powershell(monkeypatch):
    monkeypatch.setenv("UV_CACHE_DIR", str(ROOT / ".local/uv-cache"))
    hook = HOOKS["PreToolUse"][0]["hooks"][0]
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", hook["command"]],
        input=json.dumps({"tool_input": {"command": "git commit -m 'bad title'"}}),
        cwd=ROOT / "src/core",
        capture_output=True,
        text=True,
        timeout=hook["timeout"],
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["hookEventName"] == "PreToolUse"
    assert output["permissionDecision"] == "deny"
    assert "must be '[<type>] <title>'" in output["permissionDecisionReason"]
