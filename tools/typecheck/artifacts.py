"""Verify that generated typing artifacts still match their recorded build."""

import hashlib
import json
import os

from typing_inputs import require_current


def artifact_hashes(directory):
    files = sorted(
        {
            *directory.rglob("*.py"),
            *directory.rglob("*.pyi"),
            *directory.glob("registry.json"),
            *directory.glob("xmlids.json"),
            *directory.glob("source-hashes.json"),
            directory / "pyrightconfig.json",
        }
    )
    return {
        path.relative_to(directory).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in files
    }


def validate(root, directory):
    marker = json.loads((directory / "build.json").read_text(encoding="utf-8"))
    if (
        not isinstance(marker, dict)
        or not {"workspace", "image", "artifacts"} <= marker.keys()
    ):
        raise ValueError("Typing build metadata is incomplete.")
    if marker["workspace"] != os.path.normcase(str(root.resolve())):
        raise ValueError("Typing artifacts belong to a different checkout.")
    require_current(root, directory, marker["image"])
    if marker["artifacts"] != artifact_hashes(directory):
        raise ValueError(
            "Typing artifacts are missing or changed; regenerate them before checking types."
        )
    return marker
