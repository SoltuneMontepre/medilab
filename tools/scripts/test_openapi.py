"""test:openapi: refuse a change of the OpenAPI document that breaks it against a base revision, unless the change gives
the document a new version. Runs on the host through uv; oasdiff runs in its pinned image.

Usage: test_openapi.py <document> <oasdiff image> <base revision>
"""

import pathlib
import subprocess
import sys

import yaml

# Where the two documents are written for oasdiff, which reads them from a mounted folder.
WORK_DIR = pathlib.Path(".local/openapi")


def main(document, image, base):
    shown = subprocess.run(
        ["git", "show", f"{base}:{document}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if shown.returncode:
        print(f"{base} has no {document}; there is nothing to compare it with.")
        return 0
    revision = pathlib.Path(document).read_text(encoding="utf-8")
    old_version = yaml.safe_load(shown.stdout)["info"]["version"]
    new_version = yaml.safe_load(revision)["info"]["version"]
    if old_version != new_version:
        print(
            f"The document's version changes from {old_version} to {new_version}, so it may break the old one."
        )
        return 0
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    (WORK_DIR / "base.yaml").write_text(shown.stdout, encoding="utf-8")
    (WORK_DIR / "revision.yaml").write_text(revision, encoding="utf-8")
    command = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{WORK_DIR.resolve()}:/specs:ro,z",
        image,
        "breaking",
    ]
    result = subprocess.run(
        [*command, "/specs/base.yaml", "/specs/revision.yaml", "--fail-on", "ERR"],
        check=False,
    )
    if result.returncode:
        print(
            f"The document breaks version {old_version} of {base}: give it a new version, or keep the change compatible."
        )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
