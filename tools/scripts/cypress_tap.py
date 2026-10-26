"""Run Tap through this checkout's Cypress CLI, bound to its own E2E session.
Usage: python tools/scripts/cypress_tap.py <tap command> [options].
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "src/tests"
COMMANDS = frozenset(("sessions", "status", "specs", "run", "reporter", "command", "pin", "dom", "aria", "inspect"))
HELP = """Usage: task test:e2e:tap TAP_ARGS="<command> [options]"
Commands: sessions, status, specs, run, reporter, command, pin, dom, aria, inspect.
Start this worktree's session with task test:e2e:tap:open.
Use --session <pid> when this project has more than one E2E session.
Tap run dispatches asynchronously; read a fresh status and reporter for the verdict.
Guide: docs/workflows/cypress-tap.md
"""


class TapError(RuntimeError):
    pass


def invoke(arguments, *, capture=False):
    node = shutil.which("node")
    cli = TESTS / "node_modules/cypress/bin/cypress"
    metadata = TESTS / "node_modules/cypress/package.json"
    if not node or not cli.is_file() or not metadata.is_file():
        raise TapError("Install Node.js and run task test:e2e:tap:open to prepare this worktree's Cypress.")
    version = json.loads(metadata.read_text(encoding="utf-8")).get("version", "")
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if not match or tuple(map(int, match.groups())) < (15, 21, 0):
        raise TapError("Cypress Tap requires the installed project version to be 15.21.0 or newer.")
    env = os.environ.copy()
    env.pop("ELECTRON_RUN_AS_NODE", None)
    return subprocess.run(
        [node, str(cli), "tap", *arguments],
        cwd=TESTS,
        env=env,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        check=False,
    )


def extract_session(arguments):
    forwarded = []
    requested = None
    position = 0
    while position < len(arguments):
        argument = arguments[position]
        if argument in ("--session", "-s"):
            position += 1
            if position == len(arguments):
                raise TapError("--session needs the PID returned by tap sessions.")
            value = arguments[position]
        elif argument.startswith("--session="):
            value = argument.split("=", 1)[1]
        else:
            forwarded.append(argument)
            position += 1
            continue
        if requested is not None or not value.isdecimal() or int(value) <= 0:
            raise TapError("Supply one positive session PID returned by tap sessions.")
        requested = int(value)
        position += 1
    return forwarded, requested


def project_sessions(rows):
    expected = os.path.normcase(os.path.realpath(TESTS))
    return [
        row
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("projectRoot"), str)
        and os.path.normcase(os.path.realpath(row["projectRoot"])) == expected
        and row.get("testingType") == "e2e"
        and isinstance(row.get("pid"), int)
        and row["pid"] > 0
    ]


def run(arguments=None):
    if arguments is None:
        arguments = sys.argv[1:] or shlex.split(os.environ.get("MEDILAB_TAP_ARGS", ""))
    else:
        arguments = list(arguments)
    if not arguments or arguments[0] in ("-h", "--help"):
        print(HELP)
        return 0
    if arguments[0] not in COMMANDS:
        raise TapError(f"Unknown Tap command: {arguments[0]}. Run task test:e2e:tap TAP_ARGS=--help.")
    if "-h" in arguments[1:] or "--help" in arguments[1:]:
        return invoke(arguments).returncode
    arguments, requested = extract_session(arguments)
    discovery = invoke(["sessions", "--json"], capture=True)
    if discovery.returncode:
        sys.stdout.write(discovery.stdout)
        sys.stderr.write(discovery.stderr)
        return discovery.returncode
    try:
        rows = json.loads(discovery.stdout)
    except json.JSONDecodeError as error:
        raise TapError("No usable Tap session data. Start task test:e2e:tap:open and retry.") from error
    if not isinstance(rows, list):
        raise TapError("Tap returned an unexpected sessions payload.")
    matches = project_sessions(rows)
    if arguments[0] == "sessions":
        print(json.dumps(matches, indent=2))
        return 0
    candidates = [row for row in matches if requested is None or row["pid"] == requested]
    if not candidates:
        raise TapError("No matching E2E session for this worktree. Start task test:e2e:tap:open.")
    if len(candidates) != 1:
        raise TapError("Several E2E sessions match. Use tap sessions and pass --session <pid>.")
    selected = candidates[0]
    if selected.get("browserSupported") is False:
        raise TapError("Tap needs Electron, Chrome, Chromium or Edge. Start task test:e2e:tap:open.")
    return invoke([*arguments, "--session", str(selected["pid"])]).returncode


def main():
    try:
        return run()
    except (TapError, OSError, ValueError) as error:
        print(f"Cypress Tap: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
