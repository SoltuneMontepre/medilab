"""One real DOCX keyboard save on the selected owned stack; never invoke the credential-routing runner.

Plan writes only a private manifest. Run needs that reviewed manifest and creates only its named test resources.
"""

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from xml.etree.ElementTree import ParseError

from tools.onlyoffice_integration.managed_api import (
    ManagedApi,
    ProbeError,
    assert_saved,
    docx_text,
    require,
)
from tools.scripts.local_private_paths import (
    ensure_local_directory,
    guard_local_path,
    protect_created_path,
)

from .managed_process import run_owned

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / ".local/onlyoffice-managed"
TOOLS = ROOT / ".local/onlyoffice-tools"
FIXTURE = ROOT / ".local/odoo-source/odoo/addons/base/tests/files/file.docx"
VERSION = "1.56.1"
ACTOR = "demo.tester"


def digest(content):
    return hashlib.sha256(content).hexdigest()


def write_json(path, value):
    path = guard_local_path(ROOT, path)
    descriptor, name = tempfile.mkstemp(prefix=".managed-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        protect_created_path(ROOT, temporary)
        guard_local_path(ROOT, path)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def unique_fixture(nonce):
    require(
        isinstance(nonce, str) and re.fullmatch(r"[a-f0-9]{32}", nonce),
        "The fixture nonce is invalid.",
    )
    require(
        FIXTURE.is_file() and FIXTURE.resolve().is_relative_to(ROOT),
        "The fixed Odoo DOCX fixture is unavailable.",
    )
    source = FIXTURE.read_bytes()
    docx_text(source)
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(source)) as original,
        zipfile.ZipFile(output, "w") as prepared,
    ):
        for item in original.infolist():
            content = original.read(item.filename)
            if item.filename == "word/document.xml":
                require(
                    b"<w:body>" in content,
                    "The fixed DOCX has an unexpected document body.",
                )
                paragraph = (
                    f"<w:p><w:r><w:t>MEDILAB_BASE_{nonce}</w:t></w:r></w:p>".encode()
                )
                content = content.replace(b"<w:body>", b"<w:body>" + paragraph, 1)
            prepared.writestr(item, content)
    return output.getvalue()


def preflight():
    sys.path.insert(0, str(ROOT / "tools/scripts"))
    import onlyoffice
    from host_tools import selected_odoo_url

    project, marker, engine, environment = onlyoffice.selection(secure_engine=True)
    require(
        marker is not None and marker.get("status") == "completed",
        "A completed owned demo selection is required.",
    )
    state = onlyoffice.read_state(project, marker, engine)
    require(
        state is not None and state["status"] == "completed",
        "A completed owned editor is required.",
    )
    onlyoffice.resources(state)
    onlyoffice.verify_image(state)
    base = selected_odoo_url(require_saved_selection=True)
    runtime = onlyoffice.runtime_config(state, environment)
    expected = {
        "project": project,
        "base_owner": marker["owner"],
        "engine": engine,
        "odoo_origin": base,
        "editor_origin": runtime["public_origin"],
        "storage_origin": runtime["storage_origin"],
        "bucket": runtime["bucket"],
    }
    require(
        re.fullmatch(r"http://localhost:[1-9][0-9]{0,4}", base),
        "The managed probe requires the selected loopback origin.",
    )
    return expected


def tool_identity():
    package = guard_local_path(ROOT, TOOLS / "node_modules/playwright/package.json")
    browser = guard_local_path(ROOT, TOOLS / "chromium/chrome")
    provenance = guard_local_path(ROOT, TOOLS / "provenance/verified.json")
    require(
        package.is_file() and browser.is_file() and provenance.is_file(),
        "The reviewed private browser tools have not been provisioned.",
    )
    require(
        json.loads(package.read_text())["version"] == VERSION,
        "The Playwright package differs from the pinned version.",
    )
    proof = json.loads(provenance.read_text())
    require(
        proof["version"] == VERSION
        and proof["source_container_never_started"] is True
        and proof["source_container_removed"] is True
        and proof["browser_file_count"] > 0,
        "The private browser provisioning proof is incomplete.",
    )
    files = proof["browser_files"]
    require(
        len(files) == proof["browser_file_count"],
        "The browser inventory is incomplete.",
    )
    for relative, expected in files.items():
        name = Path(relative)
        require(
            not name.is_absolute() and ".." not in name.parts,
            "The browser inventory has a foreign path.",
        )
        file = guard_local_path(ROOT, TOOLS / "chromium" / name)
        require(
            file.is_file()
            and file.stat().st_size == expected["size"]
            and digest(file.read_bytes()) == expected["sha256"],
            "Private browser bytes changed after provisioning.",
        )
    return {
        "playwright": VERSION,
        "chrome_sha256": digest(browser.read_bytes()),
        "browser_file_count": len(files),
        "provenance_sha256": digest(provenance.read_bytes()),
        "official_image_config": proof["image"]["config_digest"],
        "official_amd64_digest": proof["image"]["official_amd64_digest"],
        "browser_archive_sha256": proof["browser_archive_sha256"],
    }


def plan():
    selection = preflight()
    tools = tool_identity()
    nonce = uuid.uuid4().hex
    output = ensure_local_directory(ROOT, DIRECTORY / nonce)
    manifest = {
        "format": 1,
        "nonce": nonce,
        "worktree": str(ROOT),
        "selection": selection,
        "actor": ACTOR,
        "folder_name": "MEDILAB_GUI_" + nonce,
        "file_name": "managed-proof.docx",
        "edit_marker": "MEDILAB_MANAGED_" + nonce,
        "fixture_sha256": digest(unique_fixture(nonce)),
        "tools": tools,
        "browser_policy": {
            "chromiumSandbox": True,
            "headless": True,
            "security_args": [],
        },
        "status": "planned",
        "stage": "plan_only",
        "expected_new_resources": {
            "device": 1,
            "folder": 1,
            "file": 1,
            "upload": 1,
            "editing_session": 1,
            "content_objects": 2,
            "initial_version": 1,
            "edited_version": 1,
            "initial_content_unique_marker": "MEDILAB_BASE_" + nonce,
            "browser": "one automated real Chromium profile; no native/manual GUI acceptance",
        },
    }
    path = output / "manifest.json"
    write_json(path, manifest)
    return path


def load_manifest(argument):
    lexical = Path(os.path.abspath(argument))
    require(
        lexical.parent.parent == DIRECTORY
        and lexical.name == "manifest.json"
        and re.fullmatch(r"[a-f0-9]{32}", lexical.parent.name),
        "The probe accepts only its canonical owned manifest path.",
    )
    path = guard_local_path(ROOT, lexical)
    value = json.loads(path.read_text(encoding="utf-8"))
    require(
        value.get("format") == 1
        and value.get("worktree") == str(ROOT)
        and value.get("nonce") == path.parent.name
        and value.get("status") == "planned"
        and value.get("actor") == ACTOR
        and value.get("folder_name") == "MEDILAB_GUI_" + value["nonce"]
        and value.get("file_name") == "managed-proof.docx"
        and value.get("edit_marker") == "MEDILAB_MANAGED_" + value["nonce"],
        "The reviewed manifest identity or lifecycle is invalid.",
    )
    require(
        value["selection"] == preflight() and value["tools"] == tool_identity(),
        "The selected stack or browser tools changed after planning.",
    )
    return path, value


def browser_run(manifest, password):
    node = shutil.which("node")
    require(node is not None, "The existing Node runtime is unavailable.")
    bus = shutil.which("dbus-run-session")
    require(bus is not None, "The automated browser requires its own D-Bus session.")
    output = guard_local_path(
        ROOT, DIRECTORY / manifest["nonce"] / "browser-result.json"
    )
    require(not output.exists(), "The probe refuses an existing browser result.")
    environment = {**os.environ, "NODE_PATH": str(TOOLS / "node_modules")}
    for name in (
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "XAUTHORITY",
        "HYPRLAND_INSTANCE_SIGNATURE",
        "DBUS_SESSION_BUS_ADDRESS",
        "XDG_CURRENT_DESKTOP",
    ):
        environment.pop(name, None)
    for name, relative in (
        ("XDG_CONFIG_HOME", "browser-config"),
        ("XDG_CACHE_HOME", "browser-cache"),
        ("XDG_DATA_HOME", "browser-data"),
        ("XDG_RUNTIME_DIR", "browser-runtime"),
    ):
        environment[name] = str(ensure_local_directory(ROOT, output.parent / relative))
    try:
        response = run_owned(
            [
                bus,
                "--",
                node,
                str(ROOT / "tools/onlyoffice_integration/managed_page.cjs"),
            ],
            input=json.dumps(
                {
                    "nonce": manifest["nonce"],
                    "base": manifest["selection"]["odoo_origin"],
                    "editor": manifest["selection"]["editor_origin"],
                    "fileId": manifest["file_id"],
                    "marker": manifest["edit_marker"],
                    "login": ACTOR,
                    "password": password,
                }
            ),
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=210,
            directory=output.parent,
            nonce=manifest["nonce"],
            executable=TOOLS / "chromium/chrome",
            env=environment,
        )
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        evidence = getattr(error, "managed_evidence", {})
        write_json(
            output.with_name("browser-transport.json"),
            {
                **{
                    key: value
                    for key, value in evidence.items()
                    if key not in ("stdout", "stderr")
                },
                "stdout_sha256": digest(evidence.get("stdout", "").encode()),
                "stderr_sha256": digest(evidence.get("stderr", "").encode()),
                "result_present": output.is_file(),
            },
        )
        raise
    write_json(
        output.with_name("browser-transport.json"),
        {
            "process_exit": response.returncode,
            **(
                {"cleanup": response.managed_evidence["cleanup"]}
                if hasattr(response, "managed_evidence")
                else {}
            ),
            "stdout_bytes": len(response.stdout.encode()),
            "stderr_bytes": len(response.stderr.encode()),
            "stdout_sha256": digest(response.stdout.encode()),
            "stderr_sha256": digest(response.stderr.encode()),
            "result_present": output.is_file(),
        },
    )
    require(
        output.is_file(),
        f"The browser produced no canonical result (exit {response.returncode}).",
    )
    result = json.loads(guard_local_path(ROOT, output).read_text())
    require(
        result.get("format") == 1
        and result.get("nonce") == manifest["nonce"]
        and result.get("file_id") == manifest["file_id"],
        "The browser result belongs to another attempt or file.",
    )
    result["process_exit"] = response.returncode
    return result


def execute(argument):
    path, manifest = load_manifest(argument)

    def checkpoint(**values):
        manifest.update(values)
        write_json(path, manifest)

    selection = manifest["selection"]
    password = os.environ.get("MEDILAB_DEMO_PASSWORD", "demo")
    api = ManagedApi(
        selection["odoo_origin"],
        selection["storage_origin"],
        selection["bucket"],
        ACTOR,
        password,
    )
    lock = guard_local_path(ROOT, path.parent / "run.lock")
    descriptor = os.open(
        lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    os.close(descriptor)
    protect_created_path(ROOT, lock)
    checkpoint(status="running", stage="observer_login")
    try:
        user_id = api.browser_session()
        checkpoint(stage="owned_device", actor_id=user_id)
        checkpoint(device_id=api.sign_in(manifest["nonce"], user_id))
        checkpoint(stage="owned_folder")
        folder = api.request(
            "POST",
            "/folders",
            {"name": manifest["folder_name"]},
            idempotency=manifest["nonce"],
        )["folder"]
        require(
            folder["name"] == manifest["folder_name"] and folder["role"] == "owner",
            "The created folder identity or ownership differs.",
        )
        checkpoint(folder_id=folder["id"], stage="owned_upload")
        data = unique_fixture(manifest["nonce"])
        require(
            digest(data) == manifest["fixture_sha256"],
            "The planned DOCX fixture changed.",
        )
        initial = api.upload(folder["id"], data, manifest["nonce"], checkpoint)
        files = api.request("GET", f"/folders/{folder['id']}/files")["files"]
        require(
            len(files) == 1 and files[0]["path"] == manifest["file_name"],
            "The owned folder contains unexpected files.",
        )
        file_id = files[0]["id"]
        checkpoint(file_id=file_id, initial_version=initial, stage="real_browser")
        require(
            initial["sha256"] == digest(data)
            and initial["number"] == 1
            and api.download(folder["id"], file_id, initial["id"]) == data,
            "The initial immutable version differs from the unique fixture bytes.",
        )
        require(
            not api.sessions(file_id),
            "The newly owned file already has an editing session.",
        )
        browser = browser_run(manifest, password)
        checkpoint(browser=browser)
        require(
            browser["process_exit"] == 0 and browser.get("keyboard_edit") is True,
            "The real browser did not complete the native edit.",
        )
        checkpoint(stage="callback_commit")
        deadline = time.monotonic() + 120
        versions, sessions = [], []
        while time.monotonic() < deadline:
            versions = api.request(
                "GET", f"/folders/{folder['id']}/files/{file_id}/versions"
            )["versions"]
            sessions = api.sessions(file_id)
            if (
                len(versions) > 1
                and len(sessions) == 1
                and sessions[0]["status"] == "committed"
            ):
                break
            time.sleep(1)
        require(
            len(sessions) == 1 and sessions[0]["status"] == "committed",
            "The real callback did not commit exactly one session.",
        )
        session = sessions[0]
        require(
            session["opened_by_id"][0] == user_id
            and session["base_version_id"][0] == initial["id"]
            and session["committed_version_id"][0] == versions[0]["id"],
            "The callback session linkage or actor differs.",
        )
        content = api.download(folder["id"], file_id, versions[0]["id"])
        saved = assert_saved(
            initial, versions, content, manifest["edit_marker"], user_id
        )
        checkpoint(
            status="passed",
            stage="persisted_save_verified",
            saved=saved,
            session=session,
        )
    except (Exception, KeyboardInterrupt) as error:
        details = (
            {"failure_reason": str(error)} if isinstance(error, ProbeError) else {}
        )
        checkpoint(status="failed", failure_type=type(error).__name__, **details)
        raise
    finally:
        if "device_id" in manifest:
            try:
                result = api.request("POST", f"/devices/{manifest['device_id']}/revoke")
                require(
                    result["device"]["status"] == "revoked",
                    "The owned device was not revoked.",
                )
                checkpoint(owned_device_revoked=True)
            except Exception:
                checkpoint(status="failed", owned_device_revoked=False)
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("plan", "run"))
    parser.add_argument("--manifest")
    arguments = parser.parse_args()
    try:
        if arguments.operation == "plan":
            require(
                arguments.manifest is None,
                "Plan generates its own fresh manifest destination.",
            )
            print(plan())
        else:
            require(
                arguments.manifest is not None,
                "Run requires its reviewed owned manifest.",
            )
            execute(arguments.manifest)
            print(
                "Automated real-browser DOCX save, callback session, version and storage bytes verified."
            )
    except (
        OSError,
        ValueError,
        RuntimeError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
        ParseError,
    ) as error:
        print("Managed DOCX proof failed: " + type(error).__name__, file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
