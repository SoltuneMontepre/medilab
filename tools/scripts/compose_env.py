"""dev:setup: write the compose project of this checkout into the .env next to the compose file, which docker compose
and podman-compose read wherever they are run from. The project is the checkout's folder name, so the main checkout
stays medilab and a worktree, such as medilab-api, gets containers, a network and volumes of its own. Other lines of
the file, such as the ports a worktree sets, are kept. Runs on the host through uv.

Usage: compose_env.py <compose env file>
"""

import pathlib
import re
import subprocess
import sys

KEY = "COMPOSE_PROJECT_NAME"


def project_name():
    command = ["git", "rev-parse", "--show-toplevel"]
    top = subprocess.run(command, capture_output=True, text=True, check=True)
    folder = pathlib.Path(top.stdout.strip()).name.lower()
    # Compose takes lowercase letters, digits, dashes and underscores, starting with a letter or a digit.
    return re.sub(r"[^a-z0-9_-]", "", folder).lstrip("_-") or "medilab"


def main(path):
    env = pathlib.Path(path)
    if not env.parent.is_dir():
        # A checkout without the compose file, such as CI's sparse one, runs no stack.
        print(f"No {env.parent}; no compose project to set.")
        return
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    kept = [line for line in lines if not line.startswith(f"{KEY}=")]
    name = project_name()
    env.write_text("\n".join([f"{KEY}={name}", *kept]) + "\n", encoding="utf-8")
    print(f"Compose project of this checkout: {name} ({env}).")


if __name__ == "__main__":
    main(*sys.argv[1:])
