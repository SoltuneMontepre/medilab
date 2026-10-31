"""Identify the exact source inputs used to construct a typing registry."""

import hashlib
import json
import re
import subprocess


def fingerprint(root, image):
    files = {
        root / "src/core/uv.lock",
        root / "src/core/pyproject.toml",
        root / "src/core/modules.txt",
        root / "pyrightconfig.json",
        root / "tools/dockerfiles/prod.dockerfile",
        root / "tools/taskfiles/dev.taskfile.yml",
        root / "src/core/config/odoo.conf",
        *root.glob("src/core/modules/**/*.py"),
        *root.glob("tools/typecheck/*.py"),
        *root.glob("src/core/modules/**/*.xml"),
        *root.glob("src/core/modules/**/*.csv"),
        *root.glob("src/core/modules/**/*.json"),
        *root.glob("tools/scripts/demo_bootstrap*.py"),
    }
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    revision = subprocess.run(
        ["git", "-C", str(root / ".local/odoo-source"), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    pinned = re.search(
        r"ODOO_SOURCE_REVISION: ([0-9a-f]{40})",
        (root / "tools/taskfiles/dev.taskfile.yml").read_text(encoding="utf-8"),
    )
    if pinned is None or revision != pinned.group(1):
        raise ValueError("Odoo source revision does not match the repository pin.")
    subprocess.run(
        [
            "git",
            "-C",
            str(root / ".local/odoo-source"),
            "diff",
            "--exit-code",
            "HEAD",
            "--",
            "odoo",
            "addons",
        ],
        check=True,
        capture_output=True,
    )
    return {"source": digest.hexdigest(), "odooRevision": revision, "image": image}


def require_current(root, directory, image):
    recorded = json.loads((directory / "inputs.json").read_text(encoding="utf-8"))
    if recorded != fingerprint(root, image):
        raise ValueError(
            "Typing registry inputs changed; regenerate the registry before checking types."
        )
