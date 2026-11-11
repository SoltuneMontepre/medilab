import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import requests
from freezegun import freeze_time

from odoo import fields
from odoo.tests import tagged

from .editing_service import PUBLIC_URL, callback
from .laboratory_editing_http_case import LaboratoryEditingHttpCase
from odoo.addons.sol_laboratory.constants.laboratory_editing import (
    CALLBACK_DOCUMENT_PATH,
    CALLBACK_DOCUMENT_URI,
    CALLBACK_PREFIX,
    COMMITTED,
    ERROR,
    EXPIRED,
    JWT_HEADER,
    OPEN,
    SAVING,
    SESSION_CONFLICT,
)
from odoo.addons.sol_laboratory.constants.laboratory_files import CONFLICT, EDITED_ONLINE, SYNCED
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_CONTENT
from odoo.addons.sol_laboratory.services import laboratory_bucket, openapi_document


@tagged("post_install", "-at_install")
class TestLaboratoryEditingHttp(LaboratoryEditingHttpCase):
    """Native callback contracts and durable outcomes after normal HTTP request transactions finish."""

    def test_save_commits_a_version_and_duplicate_does_not_fetch_again(self):
        self.assertAnswer(self.send(), 200)
        self.assertAnswer(self.send(), 200)

        self.assertEqual(self.state(), ([(1, SYNCED), (2, EDITED_ONLINE)], [(COMMITTED, 2)]))
        self.assertEqual(self.source.asked, [self.saved_path])
        self.assertEqual([(v["source"], v["user_id"]) for v in self.entries()[1:]], [("api", False)])
        version_user = self.committed(lambda env: self.session(env).committed_version_id.user_id.id)
        self.assertEqual(version_user, self.editor_id)
        [saved] = self.saved_objects()
        with laboratory_bucket.read(saved["object_key"]) as chunks:
            self.assertEqual(b"".join(chunks), self.content)

    def test_temporary_failure_commits_saving_then_a_later_call_commits_the_save(self):
        self.source.answer(self.saved_path, status=503)
        self.assertAnswer(self.send(), 503)
        self.assertEqual(self.state(), ([(1, SYNCED)], [(SAVING, False)]))

        self.source.answer(self.saved_path, self.content)
        self.assertAnswer(self.send(), 200)
        self.assertEqual(self.state()[1], [(COMMITTED, 2)])

    def test_temporary_bucket_failure_commits_failed_content_then_recovers(self):
        self.bucket_proxy.failure = 503
        self.assertAnswer(self.send(), 503)
        self.assertEqual(self.state(), ([(1, SYNCED)], [(SAVING, False)]))
        self.bucket_proxy.failure = 0
        self.assertAnswer(self.send(), 200)
        self.assertEqual(self.state()[1], [(COMMITTED, 2)])

    def test_permanent_bucket_permission_failure_rolls_back_and_requires_an_operator(self):
        self.bucket_proxy.failure = 403
        self.assertAnswer(self.send(), 500)
        self.assertEqual(self.state(), ([(1, SYNCED)], [(OPEN, False)]))
        self.assertEqual(self.saved_objects(), [])

    def test_last_editor_without_write_access_keeps_bytes_and_commits_terminal_error(self):
        public_id = self.committed(lambda env: env.ref("base.public_user").id)
        self.assertAnswer(self.send(self.fields(users=[str(public_id)])), 200)
        self.assertEqual(self.state(), ([(1, SYNCED)], [(ERROR, False)]))
        [saved] = self.saved_objects()
        self.assertEqual(saved["state"], "verified")

    def test_authenticated_browser_cookie_does_not_attribute_the_callback_to_its_user(self):
        with requests.Session() as browser:
            login = browser.post(
                self.http_url + "/web/session/authenticate",
                json={
                    "jsonrpc": "2.0",
                    "method": "call",
                    "params": {"db": self.registry.db_name, "login": "admin", "password": "admin"},
                },
                timeout=30,
            )
            self.assertEqual(login.json()["result"]["uid"], self.editor_id)
            self.assertAnswer(self.send(cookies=browser.cookies), 200)
        self.assertEqual(self.entries()[-1]["user_id"], False)
        self.assertEqual(self.entries()[-1]["source"], "api")

    def test_failed_fetch_keeps_an_expired_session_expired(self):
        self.committed(self.go_idle)
        self.committed(self.expire)
        self.source.answer(self.saved_path, status=404)

        self.assertAnswer(self.send(), 503)
        self.assertEqual(self.state(), ([(1, SYNCED)], [(EXPIRED, False)]))

    def test_interrupted_stream_commits_failed_staging_content_and_saving(self):
        self.source.answer(
            self.saved_path,
            self.content,
            headers={"Content-Length": str(len(self.content) + 100), "Connection": "close"},
        )

        self.assertAnswer(self.send(), 503)
        self.assertEqual(self.state(), ([(1, SYNCED)], [(SAVING, False)]))
        states = self.committed(
            lambda env: env[MODEL_LABORATORY_CONTENT].search([("id", ">", self.last_content_id)]).mapped("state")
        )
        self.assertIn("failed", states)

    def test_invalid_expired_or_mismatched_tokens_never_mutate_or_fetch(self):
        good_body, good_header = callback(self.fields())
        assert good_header is not None
        expired_body, expired_header = callback(self.fields(), lifetime=-120)
        wrong_body, wrong_header = callback(self.fields(), secret="other-test-secret-01234567890123456789")
        mismatched = {**good_body, "users": ["999999"]}
        for body, header in (
            (self.fields(), None),
            (expired_body, expired_header),
            (wrong_body, wrong_header),
            (good_body, "Bearer invalid"),
            (mismatched, good_header),
            (good_body, good_header.replace("Bearer ", "bearer ")),
        ):
            with self.subTest(header_present=bool(header)):
                self.assertAnswer(
                    requests.post(
                        self.http_url + CALLBACK_PREFIX + self.callback_token,
                        json=body,
                        headers={JWT_HEADER: header} if header else {},
                        timeout=30,
                    ),
                    403,
                )
        self.assertAnswer(self.send(token="unknown-capability"), 403)
        for key in ("another-document", "κλειδί", "\ud800"):
            self.assertAnswer(self.send(self.fields(key=key)), 403)
        self.assertEqual(self.state(), ([(1, SYNCED)], [(OPEN, False)]))
        self.assertEqual(len(self.entries()), 1)
        self.assertEqual(self.source.asked, [])

    def test_device_authorization_header_does_not_authenticate_a_callback(self):
        _body, signed = callback(self.fields())
        self.assertAnswer(self.send(header=False, body_token=False, headers={"Authorization": signed}), 403)
        self.assertEqual(self.state()[1], [(OPEN, False)])

    def test_header_only_and_body_only_signed_activity_are_supported(self):
        for header, body_token in ((True, False), (False, True)):
            self.assertAnswer(self.send(self.fields(status=1), header=header, body_token=body_token), 200)
        body, _header = callback(self.fields(status=1), header=False)
        self.assertAnswer(
            requests.post(
                self.http_url + CALLBACK_PREFIX + self.callback_token, json={"token": body["token"]}, timeout=30
            ),
            200,
        )
        self.assertEqual(self.state()[1], [(OPEN, False)])

    def test_header_signed_fields_with_an_empty_body_match_the_documented_request(self):
        _body, header = callback(self.fields(status=1), body_token=False)
        assert header is not None
        pointer = openapi_document.request_body_pointer("receiveEditingCallback", document_path=CALLBACK_DOCUMENT_PATH)
        self.assertIsNone(
            openapi_document.schema_error(
                pointer, {}, document_path=CALLBACK_DOCUMENT_PATH, document_uri=CALLBACK_DOCUMENT_URI
            )
        )
        self.assertAnswer(
            requests.post(
                self.http_url + CALLBACK_PREFIX + self.callback_token, json={}, headers={JWT_HEADER: header}, timeout=30
            ),
            200,
        )
        self.assertEqual(self.state(), ([(1, SYNCED)], [(OPEN, False)]))
        self.assertEqual(self.source.asked, [])

    def test_malformed_or_unsupported_payloads_have_no_partial_state(self):
        for values in (
            {"status": 99},
            {"status": True},
            {"status": "2"},
            {"users": [7]},
            {"url": None},
            {"url": "https://attacker.example/output.xlsx"},
            {"history": {"changes": [{"user": "invalid"}]}},
        ):
            with self.subTest(values=values):
                self.assertAnswer(self.send(self.fields(**values)), 400)
        for body in ("{", "[]", "null"):
            self.assertAnswer(
                requests.post(
                    self.http_url + CALLBACK_PREFIX + self.callback_token,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                ),
                400,
            )
        self.assertAnswer(
            requests.post(
                self.http_url + CALLBACK_PREFIX + self.callback_token,
                data="{}",
                headers={"Content-Type": "text/plain"},
                timeout=30,
            ),
            400,
        )
        self.assertEqual(self.state(), ([(1, SYNCED)], [(OPEN, False)]))
        self.assertEqual(len(self.entries()), 1)
        self.assertEqual(self.source.asked, [])

    def test_wrong_method_and_unknown_path_use_native_errors(self):
        for method in ("GET", "OPTIONS", "PUT", "PATCH", "DELETE"):
            response = requests.request(method, self.http_url + CALLBACK_PREFIX + self.callback_token, timeout=30)
            self.assertAnswer(response, 405)
            self.assertEqual(response.headers["Allow"], "POST")
        self.assertAnswer(requests.post(self.http_url + CALLBACK_PREFIX + "unknown/route", json={}, timeout=30), 404)
        self.assertEqual(self.state()[1], [(OPEN, False)])

    def test_terminal_failure_is_acknowledged_and_audited_without_a_version(self):
        self.assertAnswer(self.send(self.fields(status=3)), 200)
        self.assertEqual(self.state(), ([(1, SYNCED)], [(ERROR, False)]))
        self.assertEqual(self.source.asked, [])
        self.assertEqual(self.entries()[-1]["source"], "api")

    def test_internal_origin_is_accepted_without_public_rewrite(self):
        self.assertAnswer(self.send(self.fields(url=self.source.url + self.saved_path)), 200)
        self.assertEqual(self.state()[1], [(COMMITTED, 2)])

    def pause_fetch(self):
        entered, release = threading.Event(), threading.Event()

        def pause(_path):
            entered.set()
            if not release.wait(timeout=20):
                raise TimeoutError("The HTTP test never released the document source.")

        self.source.before_get = pause
        self.addCleanup(release.set)
        return entered, release

    def test_concurrent_callbacks_commit_one_version_and_one_save_audit(self):
        barrier = threading.Barrier(2)
        self.source.before_get = lambda _path: barrier.wait(timeout=20) if len(self.source.asked) <= 2 else None
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _number: self.send(), range(2)))
        for response in responses:
            self.assertAnswer(response, 200)
        self.assertEqual(self.state(), ([(1, SYNCED), (2, EDITED_ONLINE)], [(COMMITTED, 2)]))
        self.assertEqual([entry["action"] for entry in self.entries()], ["create", "edit"])

    def test_upload_during_http_save_preserves_conflict_and_history(self):
        entered, release = self.pause_fetch()
        with ThreadPoolExecutor(max_workers=1) as pool:
            response = pool.submit(self.send)
            try:
                self.assertTrue(entered.wait(timeout=15))
                self.committed(lambda env: self.upload(self.file(env), "Bản tải lên trong lúc lưu"))
            finally:
                release.set()
            self.assertAnswer(response.result(timeout=60), 200)
        self.assertEqual(self.state(), ([(1, SYNCED), (2, SYNCED), (3, CONFLICT)], [(SESSION_CONFLICT, 3)]))

    def test_expiry_during_http_save_still_commits_the_version(self):
        self.committed(self.go_idle)
        entered, release = self.pause_fetch()
        with ThreadPoolExecutor(max_workers=1) as pool:
            response = pool.submit(self.send)
            try:
                self.assertTrue(entered.wait(timeout=15))
                self.committed(self.expire)
            finally:
                release.set()
            self.assertAnswer(response.result(timeout=60), 200)
        self.assertEqual(self.state()[1], [(COMMITTED, 2)])

    def test_serialization_retry_reexecutes_http_without_duplicate_state(self):
        self.attempt_trigger(1)
        self.assertAnswer(self.send(), 200)
        self.assertEqual(self.attempts(), 2)
        self.assertEqual(self.state(), ([(1, SYNCED), (2, EDITED_ONLINE)], [(COMMITTED, 2)]))
        self.assertEqual(len(self.entries()), 2)
        self.assertEqual(len(self.source.asked), 2)
        events = [
            line
            for line in self.server_messages().splitlines()
            if f"session_id={self.session_id} " in line and "outcome=committed" in line
        ]
        self.assertEqual(len(events), 1)

    def test_jwt_expiry_on_internal_retry_requests_fresh_delivery_without_accepting_expired_credentials(self):
        self.attempt_trigger(1, delay=35)
        # The first verification is within the existing 60-second clock allowance; the second is outside it.
        body, header = callback(self.fields(), lifetime=-30)
        assert header is not None
        self.assertAnswer(
            requests.post(
                self.http_url + CALLBACK_PREFIX + self.callback_token,
                json=body,
                headers={JWT_HEADER: header},
                timeout=90,
            ),
            503,
        )
        self.assertEqual(self.attempts(), 1)
        self.assertEqual(self.source.asked, [self.saved_path])
        self.assertEqual(self.state(), ([(1, SYNCED)], [(OPEN, False)]))
        self.assertEqual(self.saved_objects(), [])
        self.assertEqual(len(self.entries()), 1)
        self.assertIn(f"outcome=delivery_expired session_id={self.session_id} ", self.server_messages())
        # The rejected delivery grants no authentication cache to another HTTP request, even with the same body.
        self.assertAnswer(
            requests.post(
                self.http_url + CALLBACK_PREFIX + self.callback_token,
                json=body,
                headers={JWT_HEADER: header},
                timeout=30,
            ),
            403,
        )
        self.assertEqual(self.source.asked, [self.saved_path])
        self.assertAnswer(self.send(), 200)
        self.assertEqual(self.state(), ([(1, SYNCED), (2, EDITED_ONLINE)], [(COMMITTED, 2)]))
        self.assertEqual(len(self.entries()), 2)

    def test_access_and_error_logs_do_not_expose_capabilities_jwts_or_saved_urls(self):
        self.attempt_trigger(1, code="P0001")
        marker = "presigned-query-must-not-be-logged"
        self.assertAnswer(self.send(self.fields(url=f"{PUBLIC_URL}{self.saved_path}?signature={marker}")), 500)
        logs = self.server_messages()
        self.assertFalse(self.callback_token in logs, "The callback capability was logged.")
        self.assertFalse(marker in logs, "The saved URL query was logged.")
        self.assertNotRegex(logs, r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.")
        self.assertIn(f"outcome=internal_error session_id={self.session_id} ", logs)
        self.assertRegex(
            logs,
            rf"outcome=internal_error session_id={self.session_id} elapsed_seconds=\d+\.\d+ "
            r"correlation_id=[0-9a-f]{32} error_type=\w+",
        )

    def test_encoded_callback_path_keeps_native_contract_and_redacts_credentials(self):
        body, header = callback(self.fields(status=1))
        assert header is not None
        encoded = "/" + CALLBACK_PREFIX[1:].replace("/", "%2F")
        for path in (CALLBACK_PREFIX, encoded, encoded.replace("%2F", "%2f")):
            self.assertAnswer(
                requests.post(
                    self.http_url + path + self.callback_token, json=body, headers={JWT_HEADER: header}, timeout=30
                ),
                200,
            )
        # Logging normalization must not make a twice-encoded path a valid callback route.
        response = requests.post(
            self.http_url + encoded.replace("%", "%25") + self.callback_token,
            json=body,
            headers={JWT_HEADER: header},
            timeout=30,
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.state()[1], [(OPEN, False)])
        logs = self.server_messages()
        self.assertFalse(self.callback_token in logs, "An encoded callback path exposed its capability.")
        self.assertFalse(header in logs, "An encoded callback path exposed its JWT.")
        self.assertFalse(body["token"] in logs, "An encoded callback path exposed its body JWT.")

    def test_odoo_stack_dump_during_a_callback_redacts_its_capability(self):
        entered, release = self.pause_fetch()
        with ThreadPoolExecutor(max_workers=1) as pool:
            response = pool.submit(self.send)
            try:
                self.assertTrue(entered.wait(timeout=15))
                self.http_server.send_signal(signal.SIGQUIT)
                deadline = time.monotonic() + 5
                while "odoo.tools.misc:" not in self.server_messages() and time.monotonic() < deadline:
                    time.sleep(0.05)
                logs = self.server_messages()
                self.assertIn("odoo.tools.misc:", logs)
                self.assertFalse(self.callback_token in logs, "Odoo's background stack dump exposed the capability.")
            finally:
                release.set()
            self.assertAnswer(response.result(timeout=30), 200)
        self.assertEqual(self.state()[1], [(COMMITTED, 2)])

    def test_exhausted_retries_roll_back_database_and_leave_only_reconcilable_objects(self):
        self.attempt_trigger(5)
        self.assertAnswer(self.send(), 503)
        self.assertEqual(self.attempts(), 5)
        self.assertEqual(self.state(), ([(1, SYNCED)], [(OPEN, False)]))
        self.assertEqual(len(self.entries()), 1)
        self.assertEqual(self.saved_objects(), [])
        self.assertEqual(len(self.source.asked), 5)
        keys = set(self.owned_saved_objects())
        self.assertEqual(len(keys), 5)
        logs = self.server_messages()
        for key in keys:
            self.assertTrue(f"object_key={key} " in logs, "A rolled-back object's recovery association was lost.")
        self.assertIn(f"sha256={self.saved_sha} size={len(self.content)} ", logs)
        with freeze_time(fields.Datetime.now() + timedelta(days=2)):

            def reconcile(env):
                contents = env[MODEL_LABORATORY_CONTENT]
                findings = [payload for _key, payload in contents._reconcile_findings() if payload.get("key") in keys]
                self.assertEqual({payload["kind"] for payload in findings}, {"object"})
                self.assertEqual(len(findings), 5)
                for payload in findings:
                    contents._reconcile(payload)

            self.committed(reconcile)
        self.assertEqual(self.owned_saved_objects(), [])

    def test_a_commit_time_serialization_failure_rolls_back_without_claiming_retry_exhaustion(self):
        self.attempt_trigger(1, deferred=True)
        self.assertAnswer(self.send(), 503)
        self.assertEqual(self.attempts(), 1)
        self.assertEqual(self.state(), ([(1, SYNCED)], [(OPEN, False)]))
        self.assertEqual(self.saved_objects(), [])
        self.assertEqual(len(self.entries()), 1)
        self.assertIn(f"outcome=concurrency_failure session_id={self.session_id} ", self.server_messages())
        self.assertNotIn(f"outcome=committed session_id={self.session_id} ", self.server_messages())

    def test_unexpected_failure_rolls_back_after_bucket_write(self):
        self.attempt_trigger(1, code="P0001")
        self.assertAnswer(self.send(), 500)
        self.assertEqual(self.attempts(), 1)
        self.assertEqual(self.state(), ([(1, SYNCED)], [(OPEN, False)]))
        self.assertEqual(self.saved_objects(), [])
        self.assertEqual(len(self.entries()), 1)
