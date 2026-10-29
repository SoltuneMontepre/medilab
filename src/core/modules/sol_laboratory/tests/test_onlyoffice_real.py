"""Opt-in acceptance checks. Requires the isolated tools/onlyoffice_integration stack."""

import hashlib
import io
import json
import os
import ssl
import tempfile
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import SkipTest

import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from odoo.tests import new_test_user, tagged

from .editing_service import SECRET, callback
from .laboratory_editing_http_case import LaboratoryEditingHttpCase
from .onlyoffice_real_relay import PLUGIN_GUID, OnlyofficeRealRelay
from odoo.addons import base
from odoo.addons.sol_laboratory.constants.laboratory_editing import CALLBACK_PREFIX, JWT_HEADER
from odoo.addons.sol_laboratory.constants.laboratory_files import FILE_WRITE, MEMBER_ROLE, SYNCED
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_CONTENT, MODEL_LABORATORY_FOLDER
from odoo.addons.sol_laboratory.constants.xml_ids import LABORATORY_FILES_GROUP
from odoo.addons.sol_laboratory.services import laboratory_bucket
from odoo.addons.sol_laboratory.services.onlyoffice_jwt import sign, verify_callback


@tagged("post_install", "-at_install", "-standard", "onlyoffice_real")
class TestOnlyofficeReal(LaboratoryEditingHttpCase):
    HTTP_LIMIT_TIME_REAL = 1200

    @classmethod
    def setUpClass(cls):
        if os.environ.get("ONLYOFFICE_REAL") != "1":
            raise SkipTest("Run with tools/onlyoffice_integration/run.py; a real pinned service is required.")
        super().setUpClass()
        response = requests.get(cls.editing_internal_url() + "/healthcheck", timeout=10)
        if response.status_code != 200 or response.text.strip() != "true":
            raise AssertionError("The real Document Server is not healthy.")

    @classmethod
    def editing_internal_url(cls):
        return "https://documentserver"

    @classmethod
    def editing_public_url(cls):
        return "https://documentserver"

    def setUp(self):
        self.extension = next(
            (extension for extension in ("docx", "xlsx", "pptx") if extension in self._testMethodName), "docx"
        )
        self.marker = "MEDILAB_HARNESS_" + uuid.uuid4().hex
        super().setUp()
        self.relay = OnlyofficeRealRelay(self, self.editing_public_url(), self.marker, self.extension)
        self.addCleanup(self.save_evidence)
        configuration = self.committed(
            lambda env: self.session(env)._editor_config(
                env.ref("base.user_admin"),
                self.relay.callback_url + CALLBACK_PREFIX + self.callback_token,
            )
        )
        configuration.pop("token")
        configuration["editorConfig"]["plugins"] = {
            "autostart": [PLUGIN_GUID],
            "pluginsData": [self.relay.url + "/plugin/config.json"],
        }
        self.relay.config = {**configuration, "token": sign(configuration, SECRET, 900)}

    def prepare(self, env):
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_audit_entry")
        self.last_entry_id = env.cr.fetchone()[0]
        self.last_content_id = self.last_content(env)
        folder = env[MODEL_LABORATORY_FOLDER].create({"name": self.marker, "owner_id": env.ref("base.user_admin").id})
        file = env["medilab.laboratory.file"]._get_or_create(folder, "integration." + self.extension)
        fixture = Path(base.__file__).parent / "tests/files" / ("file." + self.extension)
        self.initial_bytes = fixture.read_bytes()
        content = env[MODEL_LABORATORY_CONTENT]._new_pending()
        size, digest = laboratory_bucket.write(content.object_key, [self.initial_bytes])
        content = content._settle(digest, size)
        file._add_version(content=content, source=SYNCED, user=env.ref("base.user_admin"))
        return folder.id, file.id

    def save_evidence(self):
        directory = Path(os.environ["ONLYOFFICE_EVIDENCE_DIR"])
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        messages = self.server_messages()
        sensitive = [self.callback_token, SECRET]
        for raw, headers in self.relay.deliveries:
            fields = json.loads(raw)
            sensitive.extend(
                value for value in (fields.get("token"), fields.get("url"), headers.get(JWT_HEADER)) if value
            )
        log_redacted = all(value not in messages for value in sensitive)
        result = {
            "test": self._testMethodName,
            "extension": self.extension,
            "events": self.relay.events,
            "initial_sha256": hashlib.sha256(self.initial_bytes).hexdigest(),
            "saved": getattr(self, "saved_evidence", None),
            "final_state": self.state(),
            "odoo_sensitive_values_absent": log_redacted,
            "browser": getattr(self, "browser_result", None),
            "test_body_passed": bool(self._outcome is not None and self._outcome.success and log_redacted),
        }
        (directory / (self._testMethodName + ".json")).write_text(json.dumps(result, indent=2) + "\n")
        self.assertTrue(log_redacted, "Odoo logs retained a sensitive callback value")

    def edit_and_close(self):
        response = requests.post("http://browser:3000/edit", json={"url": self.relay.url + "/editor"}, timeout=150)
        self.browser_result = response.json()
        self.assertEqual(response.status_code, 200, "The test browser could not complete the editor plugin.")
        self.assertTrue(response.json().get("edited"))

    def wait_final(self, count=1, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            events = self.relay.final_events()
            if len(events) >= count:
                return events
            time.sleep(0.2)
        raise AssertionError(f"Expected {count} real final callbacks; got {len(self.relay.final_events())}.")

    def assert_saved(self, conflict=False):
        def read(env):
            session = self.session(env)
            version = session.committed_version_id
            return (
                session.status,
                version.sha256,
                version.content_id.object_key,
                version.user_id.id,
                len(session.file_id.version_ids),
            )

        status, digest, key, user, count = self.committed(read)
        self.assertEqual(status, "conflict" if conflict else "committed")
        self.assertEqual(user, self.editor_id)
        self.assertEqual(count, 3 if conflict else 2)
        with laboratory_bucket.read(key) as chunks:
            saved = b"".join(chunks)
        self.assertEqual(hashlib.sha256(saved).hexdigest(), digest)
        self.assertNotEqual(saved, self.initial_bytes)
        with zipfile.ZipFile(io.BytesIO(saved)) as archive:
            xml = b"\n".join(archive.read(name) for name in archive.namelist() if name.endswith(".xml"))
        self.assertIn(self.marker.encode(), xml)
        self.saved_evidence = {
            "sha256": digest,
            "bucket_sha256": hashlib.sha256(saved).hexdigest(),
            "size": len(saved),
            "session_status": status,
            "version_count": count,
            "version_user_id": user,
            "marker_present": True,
        }
        self.saved_sha = digest
        self.content = saved
        self.assertEqual(self.entries()[-1]["source"], "api")
        self.assertFalse(self.entries()[-1]["user_id"])
        self.assertTrue(all(event["jwt_consistent"] for event in self.relay.final_events()))

    def test_docx_save_and_concurrent_duplicate_callbacks(self):
        self.relay.parallel_copies = 4
        self.edit_and_close()
        self.wait_final()
        self.assert_saved()
        raw, headers = next(
            (raw, headers) for raw, headers in reversed(self.relay.deliveries) if json.loads(raw).get("status") == 2
        )

        def repeat(_index):
            return requests.post(
                self.http_url + CALLBACK_PREFIX + self.callback_token,
                data=raw,
                headers={"Content-Type": "application/json", JWT_HEADER: headers.get(JWT_HEADER, "")},
                timeout=90,
            )

        with ThreadPoolExecutor(max_workers=4) as pool:
            for response in pool.map(repeat, range(4)):
                self.assertAnswer(response, 200)
        self.assert_saved()

    def test_xlsx_save(self):
        self.edit_and_close()
        self.wait_final()
        self.assert_saved()

    def test_pptx_save(self):
        self.edit_and_close()
        self.wait_final()
        self.assert_saved()

    def test_docx_large_history_header_compatibility(self):
        configuration = dict(self.relay.config)
        configuration.pop("token")
        configuration["editorConfig"]["user"]["name"] = self.marker * 500
        self.relay.config = {**configuration, "token": sign(configuration, SECRET, 900)}
        self.edit_and_close()
        self.wait_final()
        self.assert_saved()

    def test_docx_many_editors_header_trimming(self):
        response = requests.post("http://browser:3000/edit-many", json={"url": self.relay.url + "/editor"}, timeout=300)
        self.browser_result = response.json()
        self.assertEqual(response.status_code, 200, "The multi-editor browser could not finish.")
        self.assertEqual(self.browser_result.get("editorSessions"), 27)
        events = self.wait_final()
        self.assertEqual(events[-1]["history_json_bytes"], 2)
        self.assertLess(events[-1]["header_bytes"], 7168)
        self.assert_saved()

    def test_docx_two_authorized_editors(self):
        def create_editor(env):
            user = new_test_user(env, login=self.marker, groups="base.group_user," + LABORATORY_FILES_GROUP)
            env["medilab.laboratory.folder.member"].create(
                {"folder_id": self.folder_id, "user_id": user.id, "role": MEMBER_ROLE}
            )
            self.file(env).with_user(user)._check_file_access(FILE_WRITE)
            return {"id": str(user.id), "name": user.name}

        editor = self.committed(create_editor)
        self.relay.configured_users["1"] = editor
        response = requests.post(
            "http://browser:3000/edit-many", json={"url": self.relay.url + "/editor", "participants": 1}, timeout=150
        )
        self.browser_result = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.browser_result.get("editorSessions"), 3)
        self.wait_final()
        self.assert_saved()
        raw, headers = next(
            (raw, headers) for raw, headers in reversed(self.relay.deliveries) if json.loads(raw).get("status") == 2
        )
        fields = verify_callback(json.loads(raw), headers.get(JWT_HEADER), SECRET)
        users = {change["user"]["id"] for change in fields.get("history", {}).get("changes", [])}
        self.assertTrue({str(self.editor_id), editor["id"]} <= users)

    def test_docx_503_redelivery_has_fresh_jwt(self):
        self.relay.failures = 1
        self.edit_and_close()
        events = self.wait_final(2)
        self.assertEqual([event["http"] for event in events], [503, 200])
        if "body_iat" in events[0]:
            self.assertGreater(events[1]["body_iat"], events[0]["body_iat"])
            self.assertNotEqual(events[1]["body_sha256"], events[0]["body_sha256"])
        self.assertGreater(events[1]["header_iat"], events[0]["header_iat"])
        self.assert_saved()

    def test_docx_200_error_one_does_not_retry(self):
        self.relay.negative_control = True
        self.edit_and_close()
        self.wait_final()
        time.sleep(15)
        self.assertEqual(len(self.relay.final_events()), 1)
        self.assertEqual(self.relay.final_events()[0]["error"], 1)
        self.assertEqual(self.state()[0], [(1, SYNCED)])

    def test_docx_finite_retry_exhaustion(self):
        self.relay.unavailable = True
        self.edit_and_close()
        self.wait_final(4)
        time.sleep(15)
        self.assertEqual(len(self.relay.final_events()), 4)
        self.assertEqual(self.state()[0], [(1, SYNCED)])

    def test_docx_bucket_failure_recovers_on_real_redelivery(self):
        self.bucket_proxy.failure = 503

        def restore_bucket():
            if self.relay.final_events():
                self.bucket_proxy.failure = 0

        # Runs at arrival, before forwarding the second request.
        self.relay.on_final = restore_bucket
        self.edit_and_close()
        self.wait_final(2)
        self.assert_saved()

    def test_docx_conflict_preserves_concurrent_version(self):
        concurrent = ("concurrent version " + self.marker).encode()

        def upload(env):
            content = env[MODEL_LABORATORY_CONTENT]._new_pending()
            size, digest = laboratory_bucket.write(content.object_key, [concurrent])
            content = content._settle(digest, size)
            self.file(env)._add_version(content=content, source=SYNCED, user=env.ref("base.user_admin"))
            return content.object_key, digest

        key, digest = self.committed(upload)
        self.edit_and_close()
        self.wait_final()
        self.assert_saved(conflict=True)
        with laboratory_bucket.read(key) as chunks:
            self.assertEqual(b"".join(chunks), concurrent)
        self.assertEqual(self.committed(lambda env: self.file(env).current_version_id.sha256), digest)

    def test_docx_real_jwt_expiry_on_transaction_retry(self):
        self.assert_expiry_redelivery(delay=370, timeout=480)

    def test_docx_callback_exceeds_default_worker_timeout(self):
        events = self.assert_expiry_redelivery(delay=650, timeout=760)
        self.assertGreaterEqual(events[1]["at"] - events[0]["at"], 650)

    def assert_expiry_redelivery(self, *, delay, timeout):
        ready = threading.Event()
        installed = threading.Event()

        def inject_failure():
            if not installed.is_set():
                ready.set()
                if not installed.wait(30):
                    raise AssertionError("The main test thread did not install the failure trigger.")

        self.relay.on_final = inject_failure
        self.relay.forward_timeout = timeout - 10
        self.edit_and_close()
        self.assertTrue(ready.wait(30), "No final callback arrived to install the failure trigger.")
        self.attempt_trigger(1, delay=delay)
        installed.set()
        events = self.wait_final(2, timeout=timeout)
        self.assertEqual([event["http"] for event in events], [503, 200])
        self.assertGreater(events[1]["header_iat"], events[0]["header_exp"] + 60)
        self.assertIn("outcome=delivery_expired", self.server_messages())
        self.assert_saved()
        return events

    def test_docx_captured_delivery_authentication_controls(self):
        self.edit_and_close()
        self.wait_final()
        self.assert_saved()
        raw, headers = next(
            (raw, headers) for raw, headers in reversed(self.relay.deliveries) if json.loads(raw).get("status") == 2
        )
        fields = verify_callback(json.loads(raw), headers.get(JWT_HEADER), SECRET)
        body, header = callback(fields)
        wrong_body, wrong_header = callback(fields, secret="harness-wrong-secret-01234567890123456789")
        expired, expired_header = callback(fields, lifetime=-120)
        mismatch, mismatch_header = callback({**fields, "key": "wrong-document-key"})
        altered = {**body, "users": ["99999999"]}
        for rejected_body, rejected_header in (
            (fields, None),
            (body, wrong_header),
            (wrong_body, header),
            (expired, expired_header),
            (mismatch, mismatch_header),
            (altered, header),
        ):
            response = requests.post(
                self.http_url + CALLBACK_PREFIX + self.callback_token,
                json=rejected_body,
                headers={JWT_HEADER: rejected_header} if rejected_header else {},
                timeout=90,
            )
            self.assertAnswer(response, 403)
        large = {
            **fields,
            "users": [str(self.editor_id)] * 2000,
            "history": {"changes": [{"user": {"id": str(self.editor_id), "name": "editor" * 20}}] * 2000},
        }
        body, _header = callback(large, header=False)
        self.assertAnswer(
            requests.post(self.http_url + CALLBACK_PREFIX + self.callback_token, json=body, timeout=90), 200
        )
        self.assert_saved()

    def test_docx_documentserver_refuses_untrusted_tls_source(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "runner")])
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
            .not_valid_after(datetime.now(UTC) + timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("runner")]), critical=False)
            .sign(key, hashes.SHA256())
        )
        directory = self.enterContext(tempfile.TemporaryDirectory())
        cert_path, key_path = Path(directory) / "cert.pem", Path(directory) / "key.pem"
        cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
        )
        asked = []
        content = self.initial_bytes

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                asked.append(self.path)
                self.send_response(200)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

        source = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_path, key_path)
        source.socket = context.wrap_socket(source.socket, server_side=True)
        threading.Thread(target=source.serve_forever, daemon=True).start()
        self.addCleanup(source.server_close)
        self.addCleanup(source.shutdown)
        conversion = {
            "async": False,
            "filetype": "docx",
            "outputtype": "pdf",
            "key": self.marker,
            "url": f"https://runner:{source.server_address[1]}/input.docx",
            "title": "input.docx",
        }
        response = requests.post(
            self.editing_internal_url() + "/ConvertService.ashx",
            json={**conversion, "token": sign(conversion, SECRET, 900)},
            headers={"Accept": "application/json"},
            timeout=120,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("error"), -4)
        self.assertEqual(asked, [])
        self.assertEqual(self.state()[0], [(1, SYNCED)])
