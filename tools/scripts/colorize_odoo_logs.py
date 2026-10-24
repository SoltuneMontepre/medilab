"""Stream Odoo console output, coloring only its structured severity field."""

import argparse
import os
import re
import subprocess
import sys
import threading

ODOO_LEVEL = re.compile(
    rb"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \d+ )"
    rb"(?P<before>(?:\x1b\[[0-9;]*m)*)"
    rb"(?P<level>DEBUG|INFO|SUCCESS|WARNING|WARN|ERROR|CRITICAL|FATAL)"
    rb"(?P<after>(?:\x1b\[[0-9;]*m)*)(?=\s)"
)
LEVEL_COLORS = {
    b"DEBUG": b"\x1b[2;90m",
    b"INFO": b"\x1b[1;36m",
    b"SUCCESS": b"\x1b[1;32m",
    b"WARNING": b"\x1b[1;33m",
    b"WARN": b"\x1b[1;33m",
    b"ERROR": b"\x1b[1;31m",
    b"CRITICAL": b"\x1b[1;31m",
    b"FATAL": b"\x1b[1;31m",
}
RESET = b"\x1b[0m"


def stream_color_enabled(stream) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    force = os.environ.get("FORCE_COLOR", "")
    if force == "0":
        return False
    if force in {"1", "2", "3"}:
        return True
    if not stream.isatty():
        return False
    term = os.environ.get("TERM")
    if term:
        return term != "dumb"
    return bool(
        os.environ.get("WT_SESSION")
        or os.environ.get("ANSICON")
        or os.environ.get("ConEmuANSI") == "ON"
        or os.environ.get("COLORTERM")
    )


def shell_status(returncode: int) -> int:
    return 128 - returncode if os.name == "posix" and returncode < 0 else returncode


def colorize(line: bytes, color: bool) -> bytes:
    match = ODOO_LEVEL.match(line)
    if match is None:
        return line
    level = match.group("level")
    replacement = LEVEL_COLORS[level] + level + RESET if color else level
    start = match.start("before")
    end = match.end("after")
    return line[:start] + replacement + line[end:]


def _could_start_odoo_record(pending: bytearray) -> bool:
    shape = b"0000-00-00 00:00:00,000 "
    for actual, expected in zip(pending, shape, strict=False):
        if expected == ord("0"):
            if not 48 <= actual <= 57:
                return False
        elif actual != expected:
            return False
    return True


def forward(source, destination, color: bool) -> None:
    pending = bytearray()
    while chunk := source.read1(4096):
        pending.extend(chunk)
        while pending:
            newline = pending.find(b"\n")
            if newline >= 0:
                end = newline + 1
                line = bytes(pending[:end])
                del pending[:end]
                destination.write(colorize(line, color))
                destination.flush()
            elif _could_start_odoo_record(pending):
                break
            else:
                destination.write(pending)
                destination.flush()
                pending.clear()
    if pending:
        destination.write(colorize(bytes(pending), color))
        destination.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stdout-color", choices=["true", "false", "auto"], required=True
    )
    parser.add_argument(
        "--stderr-color", choices=["true", "false", "auto"], required=True
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")

    stdout_color = (
        stream_color_enabled(sys.stdout)
        if args.stdout_color == "auto"
        else args.stdout_color == "true"
    )
    stderr_color = (
        stream_color_enabled(sys.stderr)
        if args.stderr_color == "auto"
        else args.stderr_color == "true"
    )
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdout is not None and process.stderr is not None
    forwarders = (
        threading.Thread(
            target=forward, args=(process.stdout, sys.stdout.buffer, stdout_color)
        ),
        threading.Thread(
            target=forward, args=(process.stderr, sys.stderr.buffer, stderr_color)
        ),
    )
    for thread in forwarders:
        thread.start()
    for thread in forwarders:
        thread.join()
    return shell_status(process.wait())


if __name__ == "__main__":
    raise SystemExit(main())
