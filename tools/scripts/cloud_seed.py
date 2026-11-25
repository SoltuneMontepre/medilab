"""cloud:seed: save the volumes of a completed fresh demo setup as the seed database of Claude Code cloud sessions.

Runs on the host after `task setup:fresh`, as cd-seed does. Stops the stack, then writes one tar file per volume and the
commit the seed was made from into the directory, which tools/dockerfiles/seed.dockerfile packs into an image.

Usage: python tools/scripts/cloud_seed.py <directory>
"""

import json
import subprocess
import sys
from pathlib import Path

from demo_bootstrap import COMPOSE, MARKER, ROOT

# The volumes a seed holds: the tar file of each, its Compose volume and the bootstrap setting that names it.
SEED_VOLUMES = (
    ("db.tar", "medilab-db", "MEDILAB_DB_VOLUME"),
    ("app.tar", "medilab-app", "MEDILAB_APP_VOLUME"),
    ("garage.tar", "medilab-garage", "MEDILAB_GARAGE_VOLUME"),
)
COMMIT_FILE = "commit"


def compose_config():
    """The resolved Compose configuration of this checkout's stack."""
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), "config", "--format", "json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def tar_image(config):
    """The PostgreSQL image of the stack, which also has tar to copy the volumes with."""
    return config["services"]["postgres"]["image"]


def tar_volume(image, volume, directory, arguments):
    """Run tar in a throwaway container with the volume at /volume and the directory at /seed."""
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{volume}:/volume",
            "-v",
            f"{Path(directory).resolve()}:/seed",
            image,
            "tar",
            *arguments,
        ],
        check=True,
    )


def export(directory):
    marker = json.loads(MARKER.read_text(encoding="utf-8"))
    if marker.get("status") != "completed":
        raise SystemExit("cloud:seed needs a completed `task setup:fresh`.")
    subprocess.run(
        [sys.executable, str(ROOT / "tools/scripts/local_compose.py"), "stop"],
        check=True,
    )
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    image = tar_image(compose_config())
    for file, _volume, key in SEED_VOLUMES:
        tar_volume(
            image,
            marker["config"][key],
            directory,
            ["-cf", f"/seed/{file}", "-C", "/volume", "."],
        )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    (directory / COMMIT_FILE).write_text(commit + "\n", encoding="utf-8")
    print(f"Seed of {commit} written to {directory}.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__.strip().splitlines()[-1])
    export(sys.argv[1])
