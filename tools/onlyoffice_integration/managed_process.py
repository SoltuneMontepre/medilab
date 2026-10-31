"""Bounded cleanup for the wrapper session and Playwright's detached browser group."""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path


def identity(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return {
            "pid": pid,
            "state": fields[0],
            "parent": int(fields[1]),
            "group": int(fields[2]),
            "session": int(fields[3]),
            "start_ticks": int(fields[19]),
        }
    except (OSError, ValueError, IndexError):
        return None


def group_matches(expected):
    actual = identity(expected["pid"])
    return actual is not None and all(
        actual[key] == expected[key]
        for key in ("pid", "group", "session", "start_ticks")
    )


def browser_group(directory, nonce, launcher_group, executable):
    try:
        record = json.loads((directory / "browser-launch.json").read_text())
        valid = (
            record["nonce"] == nonce
            and record["launcher_group"] == launcher_group
            and type(record["pid"]) is int
            and record["pid"] > 1
            and record["pid"] == record["group"] == record["session"]
            and group_matches(record)
        )
        if not valid:
            return None
        current = Path(f"/proc/{record['pid']}/exe").resolve(strict=True)
        interpreter = shutil.which("python3")
        permitted = {executable.resolve(), Path(sys.executable).resolve()}
        if interpreter:
            permitted.add(Path(interpreter).resolve())
        if current not in permitted:
            return None
        return record
    except (OSError, ValueError, KeyError, TypeError):
        return None


def wait_for_browser_exit(browser, cleanup):
    deadline = time.monotonic() + 3
    while browser and time.monotonic() < deadline:
        current = identity(browser["pid"])
        if (
            current is None
            or current["start_ticks"] != browser["start_ticks"]
            or current["state"] == "Z"
        ):
            break
        time.sleep(0.05)
    else:
        if browser:
            cleanup["errors"].append("OwnedBrowserStillLive")


def hard_cleanup(process, launcher, directory, nonce, executable):
    cleanup = {
        "forced": True,
        "cancel_published": False,
        "groups_signalled": [],
        "errors": [],
    }
    try:
        descriptor = os.open(
            directory / "browser-cancel",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.close(descriptor)
        cleanup["cancel_published"] = True
    except OSError as error:
        cleanup["errors"].append(type(error).__name__)
    browser = browser_group(directory, nonce, process.pid, executable)
    for value in (browser, launcher):
        try:
            if value is not None and group_matches(value):
                os.killpg(value["group"], signal.SIGKILL)
                cleanup["groups_signalled"].append(value["group"])
        except OSError as error:
            cleanup["errors"].append(type(error).__name__)
    stdout, stderr = "", ""
    try:
        stdout, stderr = process.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        cleanup["errors"].append("PipeDrainTimeout")
    cleanup["browser_record_present"] = (directory / "browser-launch.json").is_file()
    cleanup["browser_identity_validated"] = browser is not None
    wait_for_browser_exit(browser, cleanup)
    if cleanup["browser_record_present"] and browser is None:
        cleanup["errors"].append("BrowserIdentityUnverified")
    return {
        "process_exit": process.poll(),
        "cleanup": cleanup,
        "stdout": stdout,
        "stderr": stderr,
    }


def run_owned(command, *, directory, nonce, executable, timeout=210, **options):
    content = options.pop("input", None)
    if options.pop("capture_output", False):
        options["stdout"] = subprocess.PIPE
        options["stderr"] = subprocess.PIPE
    if content is not None:
        options["stdin"] = subprocess.PIPE
    process = subprocess.Popen(command, start_new_session=True, **options)
    launcher = identity(process.pid)
    failure = None
    try:
        stdout, stderr = process.communicate(input=content, timeout=timeout)
        if process.returncode == 0:
            return subprocess.CompletedProcess(
                command, process.returncode, stdout, stderr
            )
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as original:
        failure = original
    try:
        evidence = hard_cleanup(process, launcher, directory, nonce, executable)
    except (OSError, ValueError, KeyError, TypeError, IndexError) as cleanup_error:
        evidence = {
            "process_exit": process.poll(),
            "cleanup": {"forced": True, "errors": [type(cleanup_error).__name__]},
            "stdout": "",
            "stderr": "",
        }
    evidence["timed_out"] = isinstance(failure, subprocess.TimeoutExpired)
    if failure is not None:
        failure.managed_evidence = evidence
        raise failure
    response = subprocess.CompletedProcess(
        command, process.returncode, evidence["stdout"], evidence["stderr"]
    )
    response.managed_evidence = evidence
    return response
