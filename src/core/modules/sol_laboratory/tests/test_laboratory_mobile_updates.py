import base64
import json
import os
import tempfile
from email.parser import BytesParser
from email.policy import HTTP
from pathlib import Path
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, tagged

from odoo.addons.sol_laboratory.constants.mobile_updates import CATALOG_VARIABLE, DOCUMENT_PATH, DOCUMENT_URI
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_CONFIG_PARAMETER,
    MODEL_IR_HTTP,
    MODEL_RES_CONFIG_SETTINGS,
)
from odoo.addons.sol_laboratory.constants.settings import (
    MOBILE_MINIMUM_VERSION_PARAMETER,
    MOBILE_STOPPED_VERSIONS_PARAMETER,
)
from odoo.addons.sol_laboratory.services import openapi_document
from odoo.addons.sol_laboratory.services.mobile_update_http import is_mobile_update_path
from odoo.addons.sol_laboratory.tests.assertions import assert_instance

RUNTIME = "7b045729655462c0c9ff57ceb72d3ed02d9ec17c"
NEW_RUNTIME = "c0ffee5729655462c0c9ff57ceb72d3ed02d9ec1"
EXPO_HEADERS = {"expo-protocol-version": "1", "expo-platform": "android", "expo-runtime-version": RUNTIME}


def code_release(version, runtime=RUNTIME):
    manifest = json.dumps({"id": f"update-{version}", "runtimeVersion": runtime, "extra": {"version": version}})
    return {
        "platform": "android",
        "kind": "code",
        "runtime_version": runtime,
        "version": version,
        "pub_date": "2026-11-17T03:00:00.000Z",
        "manifest": manifest,
        "signature": base64.b64encode(f"signature of {version}".encode()).decode(),
    }


def install_release(version, runtime=RUNTIME):
    return {
        "platform": "android",
        "kind": "install",
        "runtime_version": runtime,
        "version": version,
        "pub_date": "2026-11-17T03:00:00+07:00",
        "url": f"https://release.example/mobile/android/{version}/medilab-{version}.apk",
        "sha256": "ab" * 32,
    }


@tagged("post_install", "-at_install")
class TestLaboratoryMobileUpdates(HttpCase):
    def setUp(self):
        super().setUp()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.catalog = Path(directory.name) / "catalog.json"
        self.write_catalog([code_release("1.0.0"), install_release("1.0.0")])
        settings = patch.dict(os.environ, {CATALOG_VARIABLE: str(self.catalog)})
        settings.start()
        self.addCleanup(settings.stop)
        self.serve()

    def write_catalog(self, releases):
        self.catalog.write_text(json.dumps({"releases": releases}))

    def serve(self, minimum="", stopped=""):
        parameters = self.env[MODEL_IR_CONFIG_PARAMETER].sudo()
        parameters.set_str(MOBILE_MINIMUM_VERSION_PARAMETER, minimum or None)
        parameters.set_str(MOBILE_STOPPED_VERSIONS_PARAMETER, stopped or None)

    def check_release(self, suffix, method="GET", data=None):
        return self.url_open(
            "/medilab/api/v1/mobile/release/" + suffix, method=method, data=data, allow_redirects=False
        )

    def check_updates(self, headers=None, method="GET"):
        return self.url_open(
            "/medilab/api/v1/mobile/updates",
            method=method,
            headers=EXPO_HEADERS if headers is None else headers,
            allow_redirects=False,
        )

    def assert_answer(self, response, status, schema="ReleaseAnswer", code=None):
        """The answer's status and headers, and its JSON body checked against the contract, which it returns."""
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        if status == 204 or response.request.method == "HEAD":
            self.assertFalse(response.content)
            return None
        body = response.json()
        schema = schema if status == 200 else "Error"
        error = openapi_document.schema_error(
            "/components/schemas/" + schema, body, document_path=DOCUMENT_PATH, document_uri=DOCUMENT_URI
        )
        self.assertIsNone(error)
        if code:
            self.assertEqual(body["error"]["code"], code)
        return body

    def release_of(self, suffix):
        return self.assert_answer(self.check_release(suffix), 200)

    def test_newer_code_update_on_the_same_runtime_and_install_on_another(self):
        self.write_catalog(
            [code_release("1.0.0"), install_release("1.0.0"), code_release("1.1.0"), install_release("1.1.0")]
        )
        self.assertEqual(self.release_of(f"android/{RUNTIME}/1.0.0"), {"action": "code", "version": "1.1.0"})
        self.assertEqual(
            self.release_of(f"android/{NEW_RUNTIME}/1.0.0"),
            {"action": "install", "version": "1.1.0", "url": install_release("1.1.0")["url"], "sha256": "ab" * 32},
        )
        self.assert_answer(self.check_release(f"android/{RUNTIME}/1.1.0"), 204)
        self.assert_answer(self.check_release(f"android/{RUNTIME}/1.0.0", method="HEAD"), 200)
        self.write_catalog(
            [code_release("1.0.0"), code_release("2.0.0", NEW_RUNTIME), install_release("2.0.0", NEW_RUNTIME)]
        )
        # A code update built for another native build cannot run on the phone, so the phone installs the new APK.
        self.assertEqual(self.release_of(f"android/{RUNTIME}/1.0.0")["action"], "install")

    def test_stopped_release_is_never_answered_and_rollback_republishes(self):
        self.write_catalog([code_release("1.0.0"), code_release("1.1.0")])
        self.serve(stopped="1.1.0")
        self.assert_answer(self.check_release(f"android/{RUNTIME}/1.0.0"), 204)
        update = self.check_updates()
        self.assertEqual(update.status_code, 200, update.text)
        self.assertIn(b'"update-1.0.0"', update.content)
        # The release pipeline republishes the code of 1.0.0 as 1.1.1; phones on the stopped 1.1.0 take it next check.
        self.write_catalog([code_release("1.0.0"), code_release("1.1.0"), code_release("1.1.1")])
        self.assertEqual(self.release_of(f"android/{RUNTIME}/1.1.0"), {"action": "code", "version": "1.1.1"})
        self.assertEqual(self.release_of(f"android/{RUNTIME}/1.0.0"), {"action": "code", "version": "1.1.1"})

    def test_phone_older_than_the_oldest_version_served(self):
        self.write_catalog([code_release("1.0.0"), install_release("1.2.0", NEW_RUNTIME)])
        self.serve(minimum="1.2.0")
        self.assertEqual(self.release_of(f"android/{RUNTIME}/1.0.0")["action"], "install")
        self.serve(minimum="1.2.0", stopped="1.2.0")
        self.assertEqual(self.release_of(f"android/{RUNTIME}/1.0.0"), {"action": "unavailable"})
        self.assertEqual(self.release_of(f"android/{RUNTIME}/1.0.0+build.4"), {"action": "unavailable"})
        # iOS has no release yet, so an iOS build is never refused.
        self.assert_answer(self.check_release(f"ios/{RUNTIME}/1.0.0"), 204)
        # A phone at the oldest version served opens when nothing newer is served.
        self.serve(minimum="1.0.0", stopped="1.2.0")
        self.assert_answer(self.check_release(f"android/{RUNTIME}/1.0.0"), 204)

    def test_expo_route_serves_the_signed_manifest_exactly(self):
        release = code_release("1.1.0")
        self.write_catalog([code_release("1.0.0"), release, code_release("1.2.0", NEW_RUNTIME)])
        response = self.check_updates()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["expo-protocol-version"], "1")
        self.assertEqual(response.headers["expo-sfv-version"], "0")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        content_type = response.headers["Content-Type"]
        self.assertTrue(content_type.startswith("multipart/mixed; boundary="))
        message = BytesParser(policy=HTTP).parsebytes(
            b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + response.content
        )
        parts = list(message.iter_parts())
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0].get_param("name", header="content-disposition"), "manifest")
        self.assertEqual(parts[0]["expo-signature"], f'sig="{release["signature"]}", keyid="main"')
        self.assertEqual(assert_instance(parts[0].get_payload(decode=True), bytes).decode(), release["manifest"])
        other_runtime = self.check_updates({**EXPO_HEADERS, "expo-runtime-version": "unknown"})
        self.assert_answer(other_runtime, 204)
        self.assertEqual(other_runtime.headers["expo-protocol-version"], "1")
        self.assert_answer(self.check_updates({**EXPO_HEADERS, "expo-platform": "ios"}), 204)

    def test_bad_requests_and_methods(self):
        for suffix in [
            f"windows/{RUNTIME}/1.0.0",
            "android/-runtime/1.0.0",
            f"android/{RUNTIME}/1.0",
            f"android/{RUNTIME}/1.0.0?url=https://evil.example",
        ]:
            self.assert_answer(self.check_release(suffix), 400, code="invalid_request")
        self.assert_answer(self.check_release(f"android/{RUNTIME}/1.0.0", data="body"), 400, code="invalid_request")
        for headers in [
            {},
            {**EXPO_HEADERS, "expo-protocol-version": "0"},
            {**EXPO_HEADERS, "expo-platform": "web"},
            {"expo-protocol-version": "1", "expo-platform": "android"},
        ]:
            self.assert_answer(self.check_updates(headers), 400, code="invalid_request")
        for method in ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"]:
            for response in (
                self.check_release(f"android/{RUNTIME}/1.0.0", method=method),
                self.check_updates(method=method),
            ):
                self.assert_answer(response, 405, code="method_not_allowed")
                self.assertEqual(response.headers["Allow"], "GET, HEAD")
        self.assert_answer(self.url_open("/medilab/api/v1/mobile/release/android"), 404, code="not_found")

    def test_invalid_or_missing_catalog_fails_closed(self):
        unsafe = install_release("1.1.0")
        for releases in [
            [code_release("1.1.0"), code_release("1.1.0")],
            [{**code_release("1.1.0"), "manifest": json.dumps({"runtimeVersion": NEW_RUNTIME})}],
            [{**code_release("1.1.0"), "manifest": "not-json"}],
            [{**code_release("1.1.0"), "signature": "invalid-base64!"}],
            [{**code_release("1.1.0"), "pub_date": "2026-11-17T03:00:00"}],
            [{**unsafe, "url": "http://release.example/medilab.apk"}],
            [{**unsafe, "url": "https://user:key@release.example/medilab.apk"}],
            [{**unsafe, "sha256": "AB" * 32}],
            [{**unsafe, "manifest": "{}"}],
        ]:
            self.write_catalog(releases)
            self.assert_answer(self.check_release(f"android/{RUNTIME}/1.0.0"), 503, code="update_unavailable")
            self.assert_answer(self.check_updates(), 503, code="update_unavailable")
        self.write_catalog([])
        self.assert_answer(self.check_release(f"android/{RUNTIME}/1.0.0"), 204)
        self.catalog.unlink()
        self.assert_answer(self.check_release(f"android/{RUNTIME}/1.0.0"), 503, code="update_unavailable")
        with patch.dict(os.environ, {CATALOG_VARIABLE: ""}):
            self.assert_answer(self.check_updates(), 503, code="update_unavailable")

    def test_administrator_sets_the_versions_served(self):
        self.write_catalog([code_release("1.0.0"), code_release("1.1.0")])
        settings = self.env[MODEL_RES_CONFIG_SETTINGS].create(
            {"mobile_minimum_version": "1.1.0", "mobile_stopped_versions": "1.0.1, 1.1.0"}
        )
        settings.execute()
        self.assertEqual(self.release_of(f"android/{RUNTIME}/1.0.0"), {"action": "unavailable"})
        self.env[MODEL_RES_CONFIG_SETTINGS].create(
            {"mobile_minimum_version": "", "mobile_stopped_versions": ""}
        ).execute()
        self.assertEqual(self.release_of(f"android/{RUNTIME}/1.0.0"), {"action": "code", "version": "1.1.0"})
        for values in ({"mobile_minimum_version": "latest"}, {"mobile_stopped_versions": "1.1.0, 1.2"}):
            with self.assertRaises(ValidationError):
                self.env[MODEL_RES_CONFIG_SETTINGS].create(values)

    def test_routes_are_public_and_outside_the_device_api(self):
        found = set()
        for rule in self.env[MODEL_IR_HTTP].routing_map().iter_rules():
            if not is_mobile_update_path(rule.rule):
                continue
            found.add(rule.rule)
            routing = assert_instance(getattr(rule.endpoint, "routing"), dict)
            self.assertEqual(routing["auth"], "none")
            self.assertIs(routing["csrf"], False)
            self.assertIs(routing["save_session"], False)
            self.assertIs(routing["readonly"], True)
        self.assertEqual(
            found,
            {
                "/medilab/api/v1/mobile/release/<string:platform>/<string:runtime_version>/<string:version>",
                "/medilab/api/v1/mobile/updates",
            },
        )
        response = self.url_open(
            f"/medilab/api/v1/mobile/release/android/{RUNTIME}/1.0.0",
            headers={"Authorization": "Bearer revoked-fixture"},
        )
        self.assert_answer(response, 204)
