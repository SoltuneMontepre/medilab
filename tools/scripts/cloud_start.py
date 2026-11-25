"""cloud:start: start Odoo in a Claude Code cloud session from the seeded demo database.

Runs on the Linux host of a cloud session. `hook` is the SessionStart hook: outside a cloud session it does nothing,
inside one it starts `run` in the background and returns at once. `run` waits for any other run to finish, starts
Docker, restores the seed when the database volume is missing or its restore did not finish, installs and upgrades
this checkout's modules, then waits until Odoo answers.

Usage: python tools/scripts/cloud_start.py hook|run
Environment: CLAUDE_CODE_REMOTE, set to true by Claude Code in a cloud session; MEDILAB_ODOO_IMAGE.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.request import urlopen

from cloud_seed import COMMIT_FILE, SEED_VOLUMES, compose_config, tar_image, tar_volume
from compose_env import main as write_compose_env
from demo_bootstrap import ROOT
from local_private_paths import ensure_local_directory

SEED_IMAGE = "ghcr.io/soltunemontepre/medilab-seed:latest"
DOCKER_CONFIG = Path("/etc/docker/daemon.json")
DOCKER_MIRROR = {"registry-mirrors": ["https://mirror.gcr.io"]}
DOCKER_LOG = Path("/var/log/dockerd.log")
SETUP_LOG = Path("/var/log/medilab-setup.log")
LOCAL = ROOT / ".local"
LOG = LOCAL / "cloud-start.log"
# The commit whose modules the last run installed, so a resumed session with the same commit skips the upgrade.
STATE = LOCAL / "cloud-start.json"
# The volumes of a restore that has not finished; the next run removes them and restores the seed again.
RESTORE_JOURNAL = LOCAL / "cloud-restore.json"
LOCK = LOCAL / "cloud-start.lock"
MODULES = ROOT / "src/core/modules.txt"
READY_MESSAGE = "Odoo is ready"


def hook():
    if os.environ.get("CLAUDE_CODE_REMOTE") != "true":
        return
    ensure_local_directory(ROOT, LOCAL)
    with LOG.open("w", encoding="utf-8") as log:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "run"],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    print(
        "Odoo is starting in the background from the seeded demo database, with this checkout's modules upgraded. "
        f"Follow .local/cloud-start.log; it ends with '{READY_MESSAGE}' or the step that failed. "
        "Run `task cloud:start` to start it again."
    )


def docker_running():
    return (
        subprocess.run(["docker", "info"], capture_output=True, check=False).returncode
        == 0
    )


def start_docker():
    if docker_running():
        return
    if not DOCKER_CONFIG.exists():
        DOCKER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        DOCKER_CONFIG.write_text(json.dumps(DOCKER_MIRROR) + "\n", encoding="utf-8")
    with DOCKER_LOG.open("a", encoding="utf-8") as log:
        subprocess.Popen(
            ["dockerd"], stdout=log, stderr=subprocess.STDOUT, start_new_session=True
        )
    for _attempt in range(30):
        if docker_running():
            return
        time.sleep(1)
    raise SystemExit(f"Docker did not start. See {DOCKER_LOG}.")


def volume_exists(name):
    """Whether Docker has the volume; an unreachable Docker raises instead of reading as a missing volume."""
    names = subprocess.run(
        ["docker", "volume", "ls", "--quiet"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return name in names


def seed_volumes(config):
    return [config["volumes"][volume]["name"] for _file, volume, _key in SEED_VOLUMES]


def restore(config):
    """Create the stack's containers and volumes, then fill the volumes from the seed image.

    The journal names the volumes until they are filled, so a run after an interrupted restore discards them first.
    """
    if subprocess.run(
        ["docker", "image", "inspect", SEED_IMAGE], capture_output=True, check=False
    ).returncode:
        subprocess.run(["docker", "pull", "-q", SEED_IMAGE], check=True)
    RESTORE_JOURNAL.write_text(
        json.dumps({"volumes": seed_volumes(config)}) + "\n", encoding="utf-8"
    )
    compose(["up", "--no-start", "--no-build", "postgres", "garage", "odoo"])
    fill_volumes(config)
    RESTORE_JOURNAL.unlink()


def discard_unfinished_restore(config):
    """Remove the containers and the volumes of a restore that did not finish, so this run restores the seed again."""
    if not RESTORE_JOURNAL.exists():
        return
    try:
        volumes = json.loads(RESTORE_JOURNAL.read_text(encoding="utf-8"))["volumes"]
    except (ValueError, KeyError):
        volumes = seed_volumes(config)
    print("Discarding the volumes of an unfinished seed restore.")
    compose(["down"])
    subprocess.run(
        ["docker", "volume", "rm", *volumes], capture_output=True, check=False
    )
    remaining = [volume for volume in volumes if volume_exists(volume)]
    if remaining:
        raise SystemExit(
            f"Could not remove the volumes of an unfinished seed restore: {', '.join(remaining)}."
        )
    RESTORE_JOURNAL.unlink()


def fill_volumes(config):
    container = subprocess.run(
        ["docker", "create", SEED_IMAGE, "seed"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    with tempfile.TemporaryDirectory(dir=LOCAL) as directory:
        try:
            subprocess.run(
                ["docker", "cp", f"{container}:/seed/.", directory], check=True
            )
        finally:
            subprocess.run(
                ["docker", "rm", container], capture_output=True, check=False
            )
        image = tar_image(config)
        for file, volume, _key in SEED_VOLUMES:
            tar_volume(
                image,
                config["volumes"][volume]["name"],
                directory,
                ["-xf", f"/seed/{file}", "-C", "/volume"],
            )
        commit = (Path(directory) / COMMIT_FILE).read_text(encoding="utf-8").strip()
    print(f"Restored the seeded demo database of {commit}.")


def compose(arguments):
    subprocess.run(
        [sys.executable, str(ROOT / "tools/scripts/local_compose.py"), *arguments],
        check=True,
    )


def modules():
    """This checkout's modules, without base, whose upgrade would upgrade every installed module."""
    names = (line.strip() for line in MODULES.read_text(encoding="utf-8").splitlines())
    return [name for name in dict.fromkeys(names) if name and name != "base"]


def task():
    executable = shutil.which("task")
    if executable is None:
        raise SystemExit("task not found. Install it with: uv tool install go-task-bin")
    return executable


def head():
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def saved_commit():
    try:
        return json.loads(STATE.read_text(encoding="utf-8")).get("commit")
    except (OSError, ValueError):
        return None


def wait_until_ready(config):
    port = config["services"]["odoo"]["ports"][0]["published"]
    url = f"http://localhost:{port}/web/login"
    for _attempt in range(120):
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    print(f"{READY_MESSAGE} at http://localhost:{port}.")
                    return
        except OSError:
            pass
        time.sleep(2)
    raise SystemExit(f"Odoo did not answer at {url}. See `task logs`.")


@contextmanager
def exclusive_lock():
    """Hold the lock of cloud:start until the block ends; the operating system releases it when the process exits."""
    import fcntl

    with LOCK.open("a", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(
                "Another cloud:start is running. Waiting for it to finish.", flush=True
            )
            fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def start():
    start_docker()
    write_compose_env()
    config = compose_config()
    discard_unfinished_restore(config)
    restored = not volume_exists(config["volumes"]["medilab-db"]["name"])
    if restored:
        restore(config)
    commit = head()
    if restored or saved_commit() != commit:
        subprocess.run(
            [task(), "upgrade", f"MODULES={','.join(modules())}"], cwd=ROOT, check=True
        )
        STATE.write_text(json.dumps({"commit": commit}) + "\n", encoding="utf-8")
    else:
        compose(["up", "-d", "--no-build"])
    wait_until_ready(config)


def run():
    problems = (
        SETUP_LOG.read_text(encoding="utf-8").strip() if SETUP_LOG.exists() else ""
    )
    if problems:
        print(f"The environment setup script reported problems:\n{problems}")
    os.chdir(ROOT)
    ensure_local_directory(ROOT, LOCAL)
    with exclusive_lock():
        start()


if __name__ == "__main__":
    commands = {"hook": hook, "run": run}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        raise SystemExit(__doc__.strip().split("\n\n")[-1].splitlines()[0])
    commands[sys.argv[1]]()
