"""Refusal and persisted-byte oracles for the opt-in managed-stack browser proof."""

import hashlib
import io
import json
import os
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from . import managed_page
from .managed_api import (
    ManagedApi,
    ProbeError,
    assert_saved,
    docx_text,
    storage_url,
    validate_new_device,
)
from .managed_http import HttpSession


def document(text):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "word/document.xml",
            (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
            ),
        )
    return output.getvalue()


class TestManagedPage(unittest.TestCase):
    def test_missing_or_foreign_browser_result_fails_with_transport_evidence(self):
        for result_nonce in (None, "b" * 32):
            with (
                self.subTest(result_nonce=result_nonce),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                directory = root / ".local/onlyoffice-managed"
                nonce = "a" * 32
                output = directory / nonce
                output.mkdir(parents=True, mode=0o700)
                manifest = {
                    "nonce": nonce,
                    "file_id": 10,
                    "edit_marker": "MEDILAB_MANAGED_" + nonce,
                    "selection": {
                        "odoo_origin": "http://localhost:24270",
                        "editor_origin": "http://localhost:30000",
                    },
                }

                def child(
                    *_arguments, result_nonce=result_nonce, output=output, **_options
                ):
                    if result_nonce:
                        (output / "browser-result.json").write_text(
                            json.dumps(
                                {"format": 1, "nonce": result_nonce, "file_id": 10}
                            )
                        )
                    return SimpleNamespace(
                        stdout="not a verdict", stderr="", returncode=1
                    )

                with (
                    patch.object(managed_page, "ROOT", root),
                    patch.object(managed_page, "DIRECTORY", directory),
                    patch.object(
                        managed_page.shutil, "which", return_value="existing-test-tool"
                    ),
                    patch.object(managed_page, "run_owned", side_effect=child),
                    self.assertRaises(ProbeError),
                ):
                    managed_page.browser_run(manifest, "synthetic-password")
                transport = json.loads((output / "browser-transport.json").read_text())
                self.assertEqual(transport["process_exit"], 1)
                self.assertEqual(transport["result_present"], result_nonce is not None)

    def test_browser_verdict_uses_nonce_bound_file_not_mixed_child_stdout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / ".local/onlyoffice-managed"
            nonce = "a" * 32
            output = directory / nonce
            output.mkdir(parents=True, mode=0o700)
            manifest = {
                "nonce": nonce,
                "file_id": 10,
                "edit_marker": "MEDILAB_MANAGED_" + nonce,
                "selection": {
                    "odoo_origin": "http://localhost:24270",
                    "editor_origin": "http://localhost:30000",
                },
            }

            def child(*_arguments, **_options):
                environment = _options["env"]
                self.assertEqual(environment["HOME"], "unchanged-personal-home")
                for name, relative in (
                    ("XDG_CONFIG_HOME", "browser-config"),
                    ("XDG_CACHE_HOME", "browser-cache"),
                    ("XDG_DATA_HOME", "browser-data"),
                    ("XDG_RUNTIME_DIR", "browser-runtime"),
                ):
                    self.assertEqual(environment[name], str(output / relative))
                for name in (
                    "DISPLAY",
                    "WAYLAND_DISPLAY",
                    "XAUTHORITY",
                    "DBUS_SESSION_BUS_ADDRESS",
                ):
                    self.assertNotIn(name, environment)
                (output / "browser-result.json").write_text(
                    json.dumps(
                        {
                            "format": 1,
                            "nonce": nonce,
                            "file_id": 10,
                            "keyboard_edit": True,
                        }
                    )
                )
                return SimpleNamespace(
                    stdout="synthetic private bus service output\n",
                    stderr="",
                    returncode=0,
                )

            with (
                patch.object(managed_page, "ROOT", root),
                patch.object(managed_page, "DIRECTORY", directory),
                patch.object(
                    managed_page.shutil, "which", return_value="existing-test-tool"
                ),
                patch.object(managed_page, "run_owned", side_effect=child),
                patch.dict(
                    os.environ,
                    {
                        "HOME": "unchanged-personal-home",
                        "DISPLAY": ":personal",
                        "WAYLAND_DISPLAY": "personal",
                        "XAUTHORITY": "personal",
                        "DBUS_SESSION_BUS_ADDRESS": "personal",
                    },
                ),
            ):
                result = managed_page.browser_run(manifest, "synthetic-password")
                self.assertEqual(result["process_exit"], 0)
                self.assertTrue(result["keyboard_edit"])
                self.assertTrue(
                    json.loads((output / "browser-transport.json").read_text())[
                        "result_present"
                    ]
                )
                with self.assertRaises(ProbeError):
                    managed_page.browser_run(manifest, "synthetic-password")

    def test_signin_candidate_must_be_new_and_match_all_manifested_device_metadata(
        self,
    ):
        nonce = "a" * 32
        device = {
            "id": 5,
            "name": "Managed browser " + nonce,
            "platform": "linux",
            "status": "signed_in",
            "current": True,
        }
        self.assertEqual(validate_new_device(device, nonce, {4}), 5)
        for values in (
            {"id": 4},
            {"id": 0},
            {"id": True},
            {"name": "personal device"},
            {"platform": "windows"},
            {"status": "revoked"},
            {"status": "active"},
            {"current": False},
            {"client_uid": "foreign"},
        ):
            with self.subTest(values=values), self.assertRaises(ProbeError):
                validate_new_device({**device, **values}, nonce, {4})

    def test_existing_client_uid_is_rejected_before_signin_can_rotate_any_key(self):
        api = ManagedApi(
            "http://localhost:24270",
            "http://localhost:24966",
            "laboratory-files",
            "demo.tester",
            "demo",
        )
        with (
            patch.object(
                api, "devices", return_value=[{"id": 4, "client_uid": "a" * 32}]
            ),
            patch.object(api, "request") as request,
            self.assertRaises(ProbeError),
        ):
            api.sign_in("a" * 32, 13)
        request.assert_not_called()
        self.assertIsNone(api.key)

    def test_wrong_signin_answer_never_becomes_eligible_for_checkpoint_or_revocation(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / ".local/onlyoffice-managed" / ("a" * 32)
            folder.mkdir(parents=True, mode=0o700)
            path = folder / "manifest.json"
            manifest = {
                "nonce": "a" * 32,
                "status": "planned",
                "selection": {
                    "odoo_origin": "http://localhost:24270",
                    "storage_origin": "http://localhost:24966",
                    "bucket": "laboratory-files",
                },
            }
            path.write_text(json.dumps(manifest))
            api = ManagedApi(
                "http://localhost:24270",
                "http://localhost:24966",
                "laboratory-files",
                "demo.tester",
                "demo",
            )
            with (
                patch.object(managed_page, "ROOT", root),
                patch.object(
                    managed_page, "load_manifest", return_value=(path, manifest)
                ),
                patch.object(managed_page, "ManagedApi", return_value=api),
                patch.object(api, "browser_session", return_value=13),
                patch.object(api, "devices", return_value=[]),
                patch.object(
                    api,
                    "request",
                    return_value={
                        "key": "synthetic-private",
                        "device": {"id": 4, "name": "personal device"},
                    },
                ) as request,
                self.assertRaises(ProbeError),
            ):
                managed_page.execute(path)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(request.call_args.args[:2], ("POST", "/sign-in"))
            self.assertNotIn("device_id", json.loads(path.read_text()))
            self.assertIsNone(api.key)

    def test_actual_http_session_keeps_cookies_local_ignores_proxy_and_refuses_redirects(
        self,
    ):
        observed = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_arguments):
                pass

            def do_GET(self):
                observed.append((self.path, self.headers.get("Cookie")))
                self.send_response(302 if self.path == "/redirect" else 200)
                if self.path == "/login":
                    self.send_header("Set-Cookie", "session_id=synthetic; Path=/")
                if self.path == "/redirect":
                    self.send_header("Location", "/must-not-be-followed")
                self.end_headers()
                self.wfile.write(b"{}")

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            origin = f"http://127.0.0.1:{server.server_port}"
            with patch.dict(
                os.environ, {"HTTP_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}
            ):
                browser, storage = HttpSession(), HttpSession()
                self.assertEqual(browser.get(origin + "/login").status_code, 200)
                self.assertEqual(browser.get(origin + "/observe").json(), {})
                storage.get(origin + "/storage")
                self.assertEqual(browser.get(origin + "/redirect").status_code, 302)
            self.assertEqual(
                observed,
                [
                    ("/login", None),
                    ("/observe", "session_id=synthetic"),
                    ("/storage", None),
                    ("/redirect", "session_id=synthetic"),
                ],
            )
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    def test_foreign_manifest_is_rejected_before_any_read_or_engine_preflight(self):
        with (
            patch.object(Path, "read_text") as read,
            patch.object(managed_page, "preflight") as preflight,
            self.assertRaises(ProbeError),
        ):
            managed_page.load_manifest("/foreign/private.json")
        read.assert_not_called()
        preflight.assert_not_called()

    def test_fixture_is_unique_deterministic_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "fixture.docx"
            original = document("UNCHANGED_FIXTURE")
            source.write_bytes(original)
            with (
                patch.object(managed_page, "ROOT", root),
                patch.object(managed_page, "FIXTURE", source),
            ):
                first = managed_page.unique_fixture("a" * 32)
                self.assertEqual(first, managed_page.unique_fixture("a" * 32))
                self.assertNotEqual(first, managed_page.unique_fixture("b" * 32))
                self.assertIn("MEDILAB_BASE_" + "a" * 32, docx_text(first))
                self.assertIn("UNCHANGED_FIXTURE", docx_text(first))
                with self.assertRaises(ProbeError):
                    managed_page.unique_fixture("</w:t>")
            self.assertEqual(source.read_bytes(), original)

    def test_storage_destinations_refuse_foreign_authority_scheme_bucket_and_credentials(
        self,
    ):
        origin = "http://localhost:24966"
        accepted = origin + "/laboratory-files/object?signature=synthetic"
        self.assertEqual(storage_url(accepted, origin, "laboratory-files"), accepted)
        for url in (
            "http://localhost:3900/laboratory-files/object",
            "https://localhost:24966/laboratory-files/object",
            "file:///laboratory-files/object",
            "http://user:key@localhost:24966/laboratory-files/object",
            origin + "/foreign/object",
            accepted + "#fragment",
        ):
            with self.subTest(url=url), self.assertRaises(ProbeError):
                storage_url(url, origin, "laboratory-files")

    def test_presigned_storage_session_never_reuses_browser_cookies_or_api_authority(
        self,
    ):
        api = ManagedApi(
            "http://localhost:24270",
            "http://localhost:24966",
            "laboratory-files",
            "demo.tester",
            "demo",
        )
        self.assertIsNot(api.bytes_http, api.http)
        self.assertFalse(api.bytes_http.cookies)
        self.assertFalse(api.bytes_http.proxy.proxies)
        self.assertIsNot(api.bytes_http.cookies, api.http.cookies)

    def test_manifest_rejects_running_or_changed_selection_before_any_api_operation(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nonce = "a" * 32
            directory = root / ".local/onlyoffice-managed"
            folder = directory / nonce
            folder.mkdir(parents=True, mode=0o700)
            manifest = folder / "manifest.json"
            value = {
                "format": 1,
                "nonce": nonce,
                "worktree": str(root),
                "status": "running",
                "actor": "demo.tester",
                "folder_name": "MEDILAB_GUI_" + nonce,
                "file_name": "managed-proof.docx",
                "edit_marker": "MEDILAB_MANAGED_" + nonce,
                "selection": {"project": "owned-before"},
                "tools": {},
            }
            manifest.write_text(json.dumps(value))
            with (
                patch.object(managed_page, "ROOT", root),
                patch.object(managed_page, "DIRECTORY", directory),
                patch.object(
                    managed_page,
                    "preflight",
                    return_value={"project": "another-project"},
                ) as preflight,
                patch.object(managed_page, "tool_identity", return_value={}),
                patch.object(ManagedApi, "request") as request,
            ):
                with self.assertRaises(ProbeError):
                    managed_page.load_manifest(manifest)
                preflight.assert_not_called()
                value["status"] = "planned"
                manifest.write_text(json.dumps(value))
                with self.assertRaises(ProbeError):
                    managed_page.load_manifest(manifest)
                request.assert_not_called()

    def test_saved_version_requires_exact_lineage_actor_hash_and_office_marker(self):
        marker = "MEDILAB_MANAGED_" + "a" * 32
        content = document(marker)
        initial = {"id": 10, "sha256": "0" * 64}
        latest = {
            "id": 11,
            "number": 2,
            "parent_version_id": 10,
            "source": "edited_online",
            "saved_by": {"id": 13},
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        }
        self.assertEqual(
            assert_saved(initial, [latest, initial], content, marker, 13)["version_id"],
            11,
        )
        for changed in (
            {"parent_version_id": 20},
            {"source": "synced"},
            {"saved_by": {"id": 14}},
            {"sha256": "f" * 64},
            {"size": 0},
        ):
            with self.subTest(changed=changed), self.assertRaises(ProbeError):
                assert_saved(
                    initial, [{**latest, **changed}, initial], content, marker, 13
                )
        with self.assertRaises(ProbeError):
            assert_saved(initial, [latest, initial, initial], content, marker, 13)
        with self.assertRaises(ProbeError):
            assert_saved(initial, [latest, initial], content, "NOT_TYPED", 13)


if __name__ == "__main__":
    unittest.main()
