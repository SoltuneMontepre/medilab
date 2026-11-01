import base64
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from odoo.addons.sol_laboratory.constants.sync_updates import (
    CATALOG_VARIABLE,
    DOCUMENT_PATH,
    DOCUMENT_URI,
    DOWNLOAD_VARIABLE,
    LEGACY_MODE_VARIABLE,
    METHODS,
)
from odoo.addons.sol_laboratory.services import openapi_document, sync_releases
from odoo.addons.sol_laboratory.services.model_lookup import dynamic_model
from odoo.addons.sol_laboratory.services.sync_update_http import is_public_sync_path
from odoo.addons.sol_laboratory.tests.assertions import assert_instance


@tagged("post_install", "-at_install")
class TestLaboratorySyncUpdates(HttpCase):
    def setUp(self):
        super().setUp()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.catalog = Path(directory.name) / "releases.json"
        self.release = {
            "target": "linux",
            "arch": "x86_64",
            "channel": "stable",
            "trust": "current",
            "version": "0.2.0",
            "url": "https://downloads.example/sync.tar.gz",
            "signature": base64.b64encode(b"signature-verified-by-the-desktop").decode(),
            "notes": "Laboratory files migration",
        }
        self.write_catalog([self.release])
        settings = patch.dict(
            os.environ,
            {
                CATALOG_VARIABLE: str(self.catalog),
                DOWNLOAD_VARIABLE: "https://downloads.example/medilab-sync",
                LEGACY_MODE_VARIABLE: "manual",
            },
        )
        settings.start()
        self.addCleanup(settings.stop)

    def write_catalog(self, releases):
        self.catalog.write_text(json.dumps({"releases": releases}))

    def call_update(self, suffix="linux/x86_64/0.1.0", method="GET", headers=None, data=None):
        return self.url_open(
            "/medilab/api/v1/updates/" + suffix, method=method, headers=headers, data=data, allow_redirects=False
        )

    def assert_response(self, response, status, code=None):
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        if status == 204 or response.request.method == "HEAD":
            self.assertFalse(response.content)
            return
        self.assertEqual(response.headers["Content-Type"], "application/json; charset=utf-8")
        schema = "Manifest" if status == 200 else "Error"
        self.assertIsNone(
            openapi_document.schema_error(
                "/components/schemas/" + schema,
                response.json(),
                document_path=DOCUMENT_PATH,
                document_uri=DOCUMENT_URI,
            )
        )
        if code:
            self.assertEqual(response.json()["error"]["code"], code)

    def test_legacy_all_paths_methods_and_credentials_refuse_without_mutation(self):
        models = ["medilab.laboratory.device", "medilab.laboratory.folder", "medilab.laboratory.file.version"]
        before = [dynamic_model(self.env, model).search_count([]) for model in models]
        for path in ["", "/", "/sign-in", "/folders/1/files/2", "/updates/linux/x86_64/0.1.0", "/unknown/deep/path"]:
            for method in [*METHODS, "PROPFIND"]:
                response = self.url_open(
                    "/api/sync/v1" + path,
                    method=method,
                    allow_redirects=False,
                    headers={"Authorization": "Bearer obsolete-fixture", "X-Sync-Device-Id": "999"},
                    data="private-fixture-body" if method not in ("GET", "HEAD") else None,
                )
                self.assert_response(response, 410, "client_update_required")
                self.assertNotIn("obsolete-fixture", response.text)
                self.assertNotIn("private-fixture-body", response.text)
                if method != "HEAD":
                    self.assertEqual(response.json()["error"]["download_url"], os.environ[DOWNLOAD_VARIABLE])
        self.assertEqual(before, [dynamic_model(self.env, model).search_count([]) for model in models])

    def test_manifest_public_selection_signature_and_no_downgrade(self):
        self.write_catalog(
            [
                self.release,
                {**self.release, "trust": "legacy", "version": "0.3.0"},
                {**self.release, "channel": "test", "version": "0.4.0-rc.1"},
                {**self.release, "target": "windows", "version": "0.5.0"},
            ]
        )
        for headers in ({}, {"Authorization": "Bearer invalid-fixture"}):
            response = self.call_update(headers=headers)
            self.assert_response(response, 200)
            self.assertEqual(response.json()["signature"], self.release["signature"])
            self.assertEqual(response.json()["version"], "0.2.0")
        self.assert_response(self.call_update("linux/x86_64/0.2.0"), 204)
        self.assert_response(self.call_update("linux/x86_64/9.0.0"), 204)
        test = self.call_update("linux/x86_64/0.1.0?channel=test")
        self.assert_response(test, 200)
        self.assertEqual(test.json()["version"], "0.4.0-rc.1")
        self.assert_response(self.call_update(method="HEAD"), 200)

    def test_legacy_manifest_requires_explicit_existing_trust(self):
        self.write_catalog([self.release, {**self.release, "trust": "legacy", "version": "0.3.0"}])
        with patch.dict(os.environ, {LEGACY_MODE_VARIABLE: "manifest"}):
            response = self.url_open("/api/sync/v1/updates/linux/x86_64/0.1.0")
            self.assert_response(response, 200)
            self.assertEqual(response.json()["version"], "0.3.0")
            self.assert_response(self.url_open("/api/sync/v1/folders"), 410, "client_update_required")
            self.assert_response(
                self.url_open("/api/sync/v1/updates/linux/x86_64/0.1.0", method="POST", data=""),
                410,
                "client_update_required",
            )

    def test_bad_requests_methods_and_missing_artifacts(self):
        for suffix in [
            "freebsd/x86_64/0.1.0",
            "linux/unknown/0.1.0",
            "linux/x86_64/not-a-version",
            "linux/x86_64/01.1.0",
            "linux/x86_64/0.1.0?channel=../x",
            "linux/x86_64/0.1.0?channel=a&channel=b",
            "linux/x86_64/0.1.0?redirect=https://evil.example",
        ]:
            self.assert_response(self.call_update(suffix), 400, "invalid_request")
        for method in ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"]:
            response = self.call_update(method=method, data="")
            self.assert_response(response, 405, "method_not_allowed")
            self.assertEqual(response.headers["Allow"], "GET, HEAD")
        self.assert_response(self.call_update(data="unexpected"), 400, "invalid_request")
        self.catalog.unlink()
        self.assert_response(self.call_update(), 503, "update_unavailable")
        self.write_catalog([])
        self.assert_response(self.call_update(), 204)

    def test_invalid_catalog_and_unsafe_downloads_fail_closed(self):
        for url in [
            "javascript:alert(1)",
            "https://user:key@downloads.example/a",
            "https://downloads.example/a?key=secret",
            "http://downloads.example/a",
            "https://downloads.example/%252e%252e/a",
            "https://downloads.example/%0a",
            "https://downloads.example/../a",
        ]:
            self.assertFalse(sync_releases.safe_download_url(url))
            with patch.dict(os.environ, {DOWNLOAD_VARIABLE: url}):
                refusal = self.url_open("/api/sync/v1")
                self.assert_response(refusal, 410, "client_update_required")
                self.assertNotIn("download_url", refusal.json()["error"])
            self.write_catalog([{**self.release, "url": url}])
            self.assert_response(self.call_update(), 503, "update_unavailable")
        for releases in [
            [self.release, self.release],
            [{**self.release, "signature": "invalid-base64!"}],
            [{**self.release, "version": "0.2.0-rc.1"}],
        ]:
            self.write_catalog(releases)
            self.assert_response(self.call_update(), 503, "update_unavailable")
        self.catalog.write_text("not-json")
        self.assert_response(self.call_update(), 503, "update_unavailable")

    def test_semver_order_and_unrelated_routes(self):
        versions = [
            "0.2.0-alpha",
            "0.2.0-alpha.1",
            "0.2.0-alpha.2",
            "0.2.0-alpha.10",
            "0.2.0-beta",
            "0.2.0-rc.1",
            "0.2.0",
        ]
        self.assertEqual(versions, sorted(versions, key=sync_releases.version_key))
        self.assertEqual(sync_releases.version_key("0.2.0+build.7"), sync_releases.version_key("0.2.0"))
        self.assertEqual(self.url_open("/api/sync/v10/sign-in", allow_redirects=False).status_code, 404)
        refused = self.url_open("/medilab/api/v1/devices", headers={"Authorization": "Bearer obsolete-fixture"})
        self.assertEqual(refused.status_code, 401)
        self.assertEqual(refused.json()["error"]["code"], "invalid_key")

    def test_public_routes_keep_their_own_authentication_boundary(self):
        found = set()
        for rule in self.env["ir.http"].routing_map().iter_rules():
            if not is_public_sync_path(rule.rule):
                continue
            found.add(rule.rule)
            routing = assert_instance(getattr(rule.endpoint, "routing"), dict)
            self.assertEqual(routing["auth"], "none")
            self.assertIs(routing["csrf"], False)
            self.assertIs(routing["save_session"], False)
            self.assertIs(routing["readonly"], True)
            self.assertNotIn("bearer_scope", routing)
        self.assertEqual(
            found,
            {
                "/api/sync/v1",
                "/api/sync/v1/",
                "/api/sync/v1/<path:legacy_path>",
                "/medilab/api/v1/updates/<string:target>/<string:arch>/<string:version>",
            },
        )
        response = self.url_open("/medilab/api/v1/updates/unknown", allow_redirects=False)
        self.assert_response(response, 404, "not_found")
