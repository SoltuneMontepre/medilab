import json
import subprocess
import sys
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
CLAUDE = json.loads((ROOT / ".mcp.json").read_text())["mcpServers"]
CURSOR = json.loads((ROOT / ".cursor/mcp.json").read_text())["mcpServers"]
CODEX = tomllib.loads((ROOT / ".codex/config.toml").read_text())["mcp_servers"]
CLIENTS = {"claude": CLAUDE, "cursor": CURSOR, "codex": CODEX}
SERENA_CONTEXTS = {"claude": "claude-code", "cursor": "ide", "codex": "ide"}


def launcher(server: dict) -> tuple[str, list[str]]:
    """The command and the arguments up to the medilab-odoo mode."""
    args = server["args"]
    return server["command"], args[: args.index("-c") + 2]


def test_every_client_starts_odoo_and_serena_through_the_same_launcher():
    expected = launcher(CLAUDE["odoo"])
    for name, servers in CLIENTS.items():
        assert launcher(servers["odoo"]) == expected, name
        assert launcher(servers["serena"]) == expected, name
        assert servers["odoo"]["args"][len(expected[1]) :] == ["mcp"], name
        serena = servers["serena"]["args"][len(expected[1]) :]
        assert serena[:2] == ["serena", "start-mcp-server"], name
        assert serena[serena.index("--context") + 1] == SERENA_CONTEXTS[name], name
        assert serena[serena.index("--project") + 1] == ".", name


def test_launcher_finds_this_checkout_from_a_subdirectory():
    script = launcher(CLAUDE["odoo"])[1][-1]
    found = script[script.index("next(") : script.rindex("), run_name")]
    probe = f"from pathlib import Path; print({found})"
    result = subprocess.run(
        [sys.executable, "-c", probe], cwd=ROOT / "src/core", capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == str(ROOT / "tools/odoo-intelligence/run.py")


def test_clients_read_the_database_without_writing():
    for name, servers in {"claude": CLAUDE, "cursor": CURSOR}.items():
        args = servers["postgres"]["args"]
        assert [arg for arg in args if arg.startswith("--access-mode")] == ["--access-mode=restricted"], name
        assert "postgres-mcp==0.3.0" in args, name
        assert not any(arg.startswith("postgres-mcp") and arg != "postgres-mcp==0.3.0" for arg in args), name


def test_claude_hooks_run_serena_from_this_worktree():
    settings = json.loads((ROOT / ".claude/settings.json").read_text())
    commands = [hook["command"] for event in settings["hooks"].values() for entry in event for hook in entry["hooks"]]
    serena = [command for command in commands if "serena-hooks" in command]
    assert len(serena) == 4
    prefix = 'uv run --locked --project "$CLAUDE_PROJECT_DIR/tools/odoo-intelligence" medilab-odoo serena-hooks '
    assert all(command.startswith(prefix) for command in serena)


def test_serena_uses_its_built_in_python_server():
    project = yaml.safe_load((ROOT / ".serena/project.yml").read_text())
    assert project["language_servers"][0] == "python"
    assert "odoo" not in project["language_servers"]
