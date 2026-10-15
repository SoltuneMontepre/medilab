"""Paths and LSP positions scoped to one checkout."""

import json
import os
import tempfile
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
RELEASE = json.loads(Path(__file__).with_name("release.json").read_text())


def utf16_position(text: str, needle: str, offset: int = 0) -> dict[str, int]:
    index = text.index(needle) + offset
    before = text[:index]
    return {"line": before.count("\n"), "character": len(before.rsplit("\n", 1)[-1].encode("utf-16-le")) // 2}


class Workspace:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.local = self.root / ".local" / "odoo-intelligence"
        self.release = self.local / "releases" / RELEASE["version"]
        self.binary = self.release / ("odoo_ls_server.exe" if os.name == "nt" else "odoo_ls_server")
        self.source = self.local / "odoo-source"

    def document(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        if Path(relative_path).is_absolute() or not path.is_relative_to(self.root):
            raise ValueError("Navigation paths must remain inside this worktree.")
        if path.suffix not in {".py", ".xml"}:
            raise ValueError("Odoo navigation accepts Python and XML documents.")
        if not path.is_file():
            raise ValueError(f"Document does not exist: {relative_path}")
        return path

    def position(self, path: Path, line: int, character: int) -> dict[str, int]:
        lines = path.read_text(encoding="utf-8").split("\n")
        if not 0 <= line < len(lines) or not 0 <= character <= len(lines[line].encode("utf-16-le")) // 2:
            raise ValueError("Position must use a valid zero-based line and UTF-16 character.")
        return {"line": line, "character": character}

    def session_directory(self) -> Path:
        logs = self.local / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix=f"session-{os.getpid()}-", dir=logs))

    def addon_snapshot(self) -> dict[str, tuple[int, int]]:
        snapshot = {}
        for directory, children, files in os.walk(self.root / "src/core/modules"):
            children[:] = [
                name
                for name in children
                if not name.startswith(".") and name not in {"__pycache__", "node_modules", "lib"}
            ]
            for name in files:
                path = Path(directory) / name
                if path.suffix not in {".py", ".xml"} or not path.resolve().is_relative_to(self.root):
                    continue
                try:
                    info = path.stat()
                    snapshot[path.as_uri()] = (info.st_mtime_ns, info.st_size)
                except FileNotFoundError:
                    continue
        return snapshot

    def addon_changes(self, before: dict, after: dict | None = None) -> list[dict]:
        after = self.addon_snapshot() if after is None else after
        changes = []
        for uri in sorted(before.keys() | after.keys()):
            if uri not in before:
                changes.append({"uri": uri, "type": 1})
            elif uri not in after:
                changes.append({"uri": uri, "type": 3})
            elif before[uri] != after[uri]:
                changes.append({"uri": uri, "type": 2})
        return changes
