"""test:upgrade: installs the modules with the released image on a throwaway database, then upgrades that database with
this checkout's image using the arguments of the production upgrade Job, and fails unless every module ends installed."""

import argparse
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KUSTOMIZATION = ROOT / "infra/cluster/odoo/kustomization.yaml"
MODULES_FILE = ROOT / "src/core/modules.txt"
REGISTRY = "ghcr.io/soltunemontepre/medilab"
POSTGRES_IMAGE = "docker.io/library/postgres:18.4"
DATABASE = "medilab"
DB_USER = "odoo"
DB_PASSWORD = "odoo"
READY_ATTEMPTS = 60


def released_image():
    match = re.search(r"^\s*newTag:\s*(\S+)\s*$", KUSTOMIZATION.read_text(), re.MULTILINE)
    if not match:
        sys.exit(f"No newTag in {KUSTOMIZATION.relative_to(ROOT)}.")
    return f"{REGISTRY}:{match.group(1)}"


def modules():
    names = [line.strip() for line in MODULES_FILE.read_text().splitlines()]
    return [name for name in names if name and name != "base"]


def docker(*args, check=True, capture=False):
    return subprocess.run(["docker", *args], check=check, text=True, stdout=subprocess.PIPE if capture else None)


def say(message):
    sys.stdout.write(f"{message}\n")
    sys.stdout.flush()


def wait_for_postgres(container):
    for _ in range(READY_ATTEMPTS):
        ready = docker("exec", container, "pg_isready", "-U", DB_USER, "-d", DATABASE, check=False, capture=True)
        if ready.returncode == 0:
            return
        time.sleep(1)
    sys.exit("Postgres did not start.")


def run_odoo(image, network, volume, postgres, odoo_args):
    say(f"\n== {image}: {' '.join(odoo_args)}")
    result = docker(
        "run", "--rm", "--network", network, "-v", f"{volume}:/var/lib/odoo",
        "-e", f"HOST={postgres}", "-e", f"USER={DB_USER}", "-e", f"PASSWORD={DB_PASSWORD}",
        image, "odoo", f"--database={DATABASE}", *odoo_args, "--max-cron-threads=0", "--stop-after-init",
        "--log-level=warn",
        check=False,
    )  # fmt: skip
    if result.returncode != 0:
        sys.exit(f"Odoo exited with {result.returncode} on {image}.")


def check_modules(postgres, expected):
    names = ",".join(expected)
    query = (
        f"select name || ' ' || state from ir_module_module where state <> 'uninstalled' or name = any('{{{names}}}')"
    )
    result = docker("exec", postgres, "psql", "-U", DB_USER, "-d", DATABASE, "-Atc", query, capture=True)
    states = dict(line.split(" ", 1) for line in result.stdout.splitlines() if line)
    wrong = {name: state for name, state in states.items() if state != "installed"}
    wrong |= {name: "missing" for name in expected if name not in states}
    if wrong:
        listed = ", ".join(f"{name} ({state})" for name, state in sorted(wrong.items()))
        sys.exit(f"Modules not installed after the upgrade: {listed}")
    say(f"\nEvery module is installed: {', '.join(expected)}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=os.environ.get("BASE_IMAGE") or released_image())
    parser.add_argument("--image", default=os.environ.get("MEDILAB_ODOO_IMAGE") or "medilab-odoo:local")
    args = parser.parse_args()

    names = modules()
    run_id = uuid.uuid4().hex[:8]
    network = f"medilab-upgrade-{run_id}"
    postgres = f"medilab-upgrade-db-{run_id}"
    volume = f"medilab-upgrade-data-{run_id}"
    say(f"Upgrading from {args.base} to {args.image}.")
    docker("pull", "-q", args.base)
    try:
        docker("network", "create", network, capture=True)
        docker("volume", "create", volume, capture=True)
        docker(
            "run", "-d", "--name", postgres, "--network", network,
            "-e", f"POSTGRES_USER={DB_USER}", "-e", f"POSTGRES_PASSWORD={DB_PASSWORD}", "-e", f"POSTGRES_DB={DATABASE}",
            POSTGRES_IMAGE,
            capture=True,
        )  # fmt: skip
        wait_for_postgres(postgres)
        init = f"--init={','.join(names)}"
        run_odoo(args.base, network, volume, postgres, [init])
        run_odoo(args.image, network, volume, postgres, [init, "--update=all"])
        check_modules(postgres, names)
    finally:
        docker("rm", "-f", "-v", postgres, check=False, capture=True)
        docker("volume", "rm", "-f", volume, check=False, capture=True)
        docker("network", "rm", network, check=False, capture=True)


if __name__ == "__main__":
    main()
