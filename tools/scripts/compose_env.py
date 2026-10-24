"""dev:setup: write this checkout's Compose identity into the .env beside the Compose file.

An explicitly selected fresh-demo project and its saved ports, image and volumes take precedence over the
worktree-derived default. Other .env lines are preserved. Runs on the host through uv.

Usage: compose_env.py
"""

import hashlib
import json
import pathlib
import re
import subprocess

KEY = "COMPOSE_PROJECT_NAME"
# The .env next to the compose file, found from this script rather than taken as an argument, so it can only ever be
# that file.
ENV_FILE = pathlib.Path(__file__).resolve().parents[1] / "infrastructure" / ".env"
MARKER = pathlib.Path(__file__).resolve().parents[2] / ".local/demo-bootstrap.json"
SWITCH_JOURNAL = MARKER.with_name("demo-bootstrap-switch.json")


def _selected_marker(root):
    if SWITCH_JOURNAL.exists():
        raise ValueError(
            "An interrupted project switch exists; run `task setup:fresh:switch:recover` before Compose operations."
        )
    if not MARKER.exists():
        return None
    try:
        marker = json.loads(MARKER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read Compose selection marker {MARKER}.") from error
    if not marker.get("selected_project"):
        return None
    if marker.get("worktree") != str(pathlib.Path(root).resolve()):
        raise ValueError("The selected Compose project belongs to another worktree.")
    project = marker.get("project", "")
    if not re.fullmatch(r"medilab-bootstrap-[a-z0-9][a-z0-9_-]{0,39}", project):
        raise ValueError("The selected Compose project has an invalid identity.")
    if marker.get("config", {}).get(KEY) != project:
        raise ValueError(
            "The selected Compose configuration has a different project identity."
        )
    return marker


def selected_project_name(root):
    marker = _selected_marker(root)
    return marker["project"] if marker else None


def worktree_paths(root):
    command = ["git", "worktree", "list", "--porcelain"]
    result = subprocess.run(
        command, cwd=root, capture_output=True, text=True, check=True
    )
    return [
        pathlib.Path(line.removeprefix("worktree ")).resolve()
        for line in result.stdout.splitlines()
        if line.startswith("worktree ")
    ]


def compose_project_name(root, worktrees):
    root = pathlib.Path(root).resolve()
    folder = root.name.lower()
    collisions = [
        pathlib.Path(path).resolve()
        for path in worktrees
        if pathlib.Path(path).name.casefold() == folder
    ]
    primary = pathlib.Path(worktrees[0]).resolve() if worktrees else root
    if len(collisions) > 1 and root != primary:
        digest = hashlib.sha256(str(root).casefold().encode()).hexdigest()[:8]
        folder = f"{folder}-{digest}"
    return re.sub(r"[^a-z0-9_-]", "", folder).lstrip("_-") or "medilab"


def project_name():
    command = ["git", "rev-parse", "--show-toplevel"]
    top = subprocess.run(command, capture_output=True, text=True, check=True)
    root = pathlib.Path(top.stdout.strip()).resolve()
    return selected_project_name(root) or compose_project_name(
        root, worktree_paths(root)
    )


def main():
    env = ENV_FILE
    if not env.parent.is_dir():
        # A checkout without the compose file, such as CI's sparse one, runs no stack.
        print(f"No {env.parent}; no compose project to set.")
        return
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    root = pathlib.Path(__file__).resolve().parents[2]
    selected = _selected_marker(root)
    values = selected["config"] if selected else {KEY: project_name()}
    kept = [line for line in lines if line.split("=", 1)[0] not in values]
    name = project_name()
    env.write_text(
        "\n".join([*(f"{key}={value}" for key, value in values.items()), *kept]) + "\n",
        encoding="utf-8",
    )
    print(f"Compose project of this checkout: {name} ({env}).")


if __name__ == "__main__":
    main()
