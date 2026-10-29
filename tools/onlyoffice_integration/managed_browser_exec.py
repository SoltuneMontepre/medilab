#!/usr/bin/env python3
"""Publish the new detached browser's kernel identity before executing pinned Chromium."""

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.onlyoffice_integration.managed_process import identity
from tools.scripts.local_private_paths import guard_local_path


def main():
    nonce = os.environ.get("MEDILAB_MANAGED_NONCE", "")
    if not re.fullmatch(r"[a-f0-9]{32}", nonce):
        raise RuntimeError("Invalid browser attempt")
    directory = guard_local_path(ROOT, ROOT / ".local/onlyoffice-managed" / nonce)
    manifest = json.loads(
        guard_local_path(ROOT, directory / "manifest.json").read_text()
    )
    if manifest["nonce"] != nonce or manifest["status"] != "running":
        raise RuntimeError("Inactive browser attempt")
    record = identity(os.getpid())
    if record["pid"] != record["group"] or record["pid"] != record["session"]:
        raise RuntimeError("Browser has no private group")
    record.update(nonce=nonce, launcher_group=os.getpgid(os.getppid()))
    temporary = guard_local_path(ROOT, directory / f".browser-launch-{os.getpid()}")
    with temporary.open("x", encoding="utf-8") as stream:
        os.chmod(temporary, 0o600)
        json.dump(record, stream)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.link(temporary, guard_local_path(ROOT, directory / "browser-launch.json"))
    finally:
        temporary.unlink()
    if guard_local_path(ROOT, directory / "browser-cancel").exists():
        return
    chrome = guard_local_path(ROOT, ROOT / ".local/onlyoffice-tools/chromium/chrome")
    os.execv(chrome, [str(chrome), *sys.argv[1:]])


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, KeyError, TypeError):
        raise SystemExit(1) from None
