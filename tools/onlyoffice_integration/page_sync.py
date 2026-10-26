"""Observe the released page's saved version through the actual Sync Rust API client in an owned fixture."""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from tools.onlyoffice_integration import run


def wait_for_desktop_ready(process):
    ready_path = run.EVIDENCE_DIRECTORY + "/desktop-ready.json"
    deadline = time.monotonic() + 300
    ready = None
    while process.poll() is None and time.monotonic() < deadline:
        result = run.command(
            [
                *run.DOCKER,
                "exec",
                run.CONTAINER,
                "python3",
                "-c",
                f"from pathlib import Path; p=Path({ready_path!r}); print(p.read_text() if p.exists() else '')",
            ],
            env=run.DOCKER_ENV,
        )
        if result.returncode == 0 and result.stdout.strip():
            ready = json.loads(result.stdout)
            break
        time.sleep(1)
    return ready


def observe_desktop_save(desktop, ready):
    container = json.loads(run.command([*run.DOCKER, "inspect", run.CONTAINER], env=run.DOCKER_ENV).stdout)[0]
    address = urlsplit(ready["url"])
    if (
        address.scheme != "http"
        or address.hostname != container["Config"]["Hostname"]
        or not address.port
        or address.path
        or address.query
        or address.fragment
        or address.username
        or not all(isinstance(ready[key], int) and ready[key] > 0 for key in ("folder", "file"))
        or not re.fullmatch(r"[a-f0-9]{64}", ready["sha256"])
    ):
        raise ValueError("The page observer did not supply an owned fixture address and version.")
    command = [*run.DOCKER, "exec", "-w", "/workspace"]
    variables = {
        "MEDILAB_E2E_URL": ready["url"],
        "MEDILAB_E2E_LOGIN": "admin",
        "MEDILAB_E2E_PASSWORD": "admin",
        "MEDILAB_E2E_EDITOR_FOLDER": str(ready["folder"]),
        "MEDILAB_E2E_EDITOR_FILE": str(ready["file"]),
        "MEDILAB_E2E_EDITOR_SHA256": ready["sha256"],
    }
    for name, value in variables.items():
        command.extend(["-e", f"{name}={value}"])
    command.extend(
        [
            desktop,
            "cargo",
            "test",
            "--locked",
            "--manifest-path",
            "src/applications/medilab-sync/src-tauri/Cargo.toml",
            "api_live_tests::live_editor_save_is_visible_to_desktop_client",
            "--",
            "--ignored",
            "--exact",
        ]
    )
    result = run.command(command, env=run.DOCKER_ENV, timeout=120)
    observed = result.returncode == 0 and "1 passed; 0 failed; 0 ignored" in result.stdout
    outcome = json.dumps({"status": "PASS" if observed else "FAIL", "desktop_client_observed_save": observed})
    run.require_success(
        run.command(
            [
                *run.DOCKER,
                "exec",
                run.CONTAINER,
                "python3",
                "-c",
                (
                    "from pathlib import Path; import sys; "
                    f"p=Path({(run.EVIDENCE_DIRECTORY + '/desktop-result.json')!r}); "
                    "q=p.with_suffix('.tmp'); q.write_text(sys.argv[1]+chr(10)); q.replace(p)"
                ),
                outcome,
            ],
            env=run.DOCKER_ENV,
        ),
        "Record desktop observation",
    )
    run.OUTPUT.mkdir(parents=True, exist_ok=True)
    summary = [
        line
        for line in (result.stdout + result.stderr).splitlines()
        if re.fullmatch(r"test [A-Za-z0-9_:]+ \.\.\. (ok|FAILED)", line) or line.startswith("test result:")
    ]
    (run.OUTPUT / "desktop-client.log").write_text("\n".join(summary) + "\n")


def main():
    desktop = os.environ["ONLYOFFICE_DESKTOP_CONTAINER"]
    if not re.fullmatch(r"medilab-integration-[a-z0-9-]+", desktop):
        raise ValueError("Select an owned integration desktop fixture.")
    if os.environ.get("ONLYOFFICE_DESKTOP_PROBE") != "1":
        raise ValueError("Enable the explicit desktop observation rendezvous.")
    process = subprocess.Popen([sys.executable, str(Path(run.__file__)), "test-native"])
    ready = wait_for_desktop_ready(process)
    if ready is not None:
        observe_desktop_save(desktop, ready)
    return process.wait(timeout=600)


if __name__ == "__main__":
    sys.exit(main())
