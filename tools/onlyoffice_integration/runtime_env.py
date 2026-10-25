"""Write a protected, test-only Node settings fixture from the committed infrastructure handoff."""

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INFRASTRUCTURE_COMMIT = "5b42e14f5715f21f85f525911cd8f692ae51302e"


def write_fixture(output, values):
    private = ROOT / ".local"
    if output.is_symlink():
        raise ValueError("A fixture output cannot be a symbolic link.")
    target = output.resolve()
    if private.is_symlink() or not target.is_relative_to(private) or target == private:
        raise ValueError("Write fixtures only beneath this worktree's .local directory.")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write("".join(key + "=" + value + "\n" for key, value in values.items()))
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default=INFRASTRUCTURE_COMMIT)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/onlyoffice-node-contract.env")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        raise ValueError("Use an exact local infrastructure commit SHA.")
    result = subprocess.run(
        ["git", "show", args.commit + ":tools/infrastructure/onlyoffice/settings.json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    settings = json.loads(result.stdout)
    source = ROOT / "src/core/modules/sol_laboratory/tests/editing_service.py"
    secret = next(
        ast.literal_eval(node.value)
        for node in ast.parse(source.read_text()).body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "SECRET" for target in node.targets)
    )
    values = {
        "JWT_ENABLED": "true",
        "JWT_SECRET": secret,
        "JWT_HEADER": "Medilab-Editor-Token",
        "JWT_IN_BODY": "false",
        "ALLOW_PRIVATE_IP_ADDRESS": "true",
        "ALLOW_META_IP_ADDRESS": "false",
        "USE_UNAUTHORIZED_STORAGE": "false",
        "NGINX_WORKER_PROCESSES": "2",
        "PLUGINS_ENABLED": "false",
        "DS_LOG_LEVEL": "OFF",
        "NGINX_ACCESS_LOG": "false",
        "NODE_CONFIG": json.dumps(settings, separators=(",", ":")),
    }
    output = write_fixture(args.output, values)
    sys.stdout.write(
        json.dumps(
            {
                "output": str(output),
                "infrastructure_commit": args.commit,
                "settings_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
            }
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
