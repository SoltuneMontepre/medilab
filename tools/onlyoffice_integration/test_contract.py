"""Local security checks of production code; these do not establish Document Server compatibility."""

import logging
import os
import secrets
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote

import jwt

from .production import load_service

SECRET = "agent4-local-test-secret-01234567890123456789"
FIELDS = {"key": "agent4-key", "status": 2, "url": "http://documentserver/cache/result.docx", "users": ["7"]}
SERVICE = load_service("onlyoffice_jwt")
URLS = load_service("editing_service_urls")
LOGGING = load_service("editing_callback_logging")


def signed(fields, *, secret=SECRET, lifetime=300):
    times = {"iat": int(time.time()), "exp": int(time.time()) + lifetime}
    body = {**fields, "token": jwt.encode({**fields, **times}, secret, algorithm="HS256")}
    header = "Bearer " + jwt.encode({"payload": fields, **times}, secret, algorithm="HS256")
    return body, header


class TestContract(unittest.TestCase):
    def refuse(self, body, header):
        with self.assertRaises(SERVICE.EditingCallbackRefused) as refusal:
            SERVICE.verify_callback(body, header, SECRET)
        self.assertNotIn(SECRET, str(refusal.exception))
        self.assertNotIn("eyJ", str(refusal.exception))
        return refusal.exception

    def test_valid_header_and_body(self):
        self.assertEqual(SERVICE.verify_callback(*signed(FIELDS), SECRET), FIELDS)

    def test_each_supported_token_location(self):
        body, header = signed(FIELDS)
        for unsigned, token in ((FIELDS, header), (body, None), ({"token": body["token"]}, None)):
            with self.subTest(location=list(unsigned)):
                self.assertEqual(SERVICE.verify_callback(unsigned, token, SECRET), FIELDS)

    def test_no_tokens(self):
        self.refuse(FIELDS, None)

    def test_invalid_signature_even_with_a_valid_other_token(self):
        body, header = signed(FIELDS)
        bad_body, bad_header = signed(FIELDS, secret="different-agent4-secret-01234567890123456789")
        self.refuse(body, bad_header)
        self.refuse(bad_body, header)

    def test_expired_rejected_and_classified(self):
        self.assertTrue(self.refuse(*signed(FIELDS, lifetime=-120)).expired)

    def test_bad_signature_is_not_classified_as_expiry(self):
        self.assertFalse(self.refuse(*signed(FIELDS, lifetime=-120, secret="x" * 40)).expired)

    def test_unsigned_key_and_url_changes(self):
        body, header = signed(FIELDS)
        for field, value in (("key", "different-key"), ("url", "http://169.254.169.254/latest/meta-data/")):
            with self.subTest(field=field):
                self.refuse({**body, field: value}, header)

    def test_header_and_body_key_disagreement(self):
        body, _ = signed({**FIELDS, "key": "other-key"})
        _, header = signed(FIELDS)
        self.refuse({"token": body["token"]}, header)

    def test_large_history_and_users_signed_without_loss(self):
        fields = {
            **FIELDS,
            "users": [str(index) for index in range(2000)],
            "history": {"changes": [{"user": {"id": str(index), "name": "editor" * 20}} for index in range(2000)]},
        }
        body, header = signed(fields)
        self.assertGreater(len(header), 100_000)
        self.assertEqual(SERVICE.verify_callback(body, header, SECRET), fields)

    def test_trimmed_header_never_authenticates_full_unsigned_history(self):
        full = {**FIELDS, "history": {"changes": [{"user": {"id": "999"}}]}}
        body, _ = signed(full)
        _, trimmed = signed(FIELDS)
        self.refuse(body, trimmed)
        self.refuse(full, trimmed)

    def test_both_trimmed_tokens_do_not_authenticate_extra_unsigned_users(self):
        body, header = signed(FIELDS)
        self.refuse({**body, "users": ["7", "999"]}, header)

    def test_claim_expiry_required(self):
        self.refuse(FIELDS, "Bearer " + jwt.encode({"payload": FIELDS}, SECRET, algorithm="HS256"))

    def test_none_and_wrong_algorithm(self):
        for algorithm, secret in (("none", None), ("HS384", SECRET * 2)):
            token = jwt.encode({"payload": FIELDS, "exp": int(time.time()) + 300}, secret, algorithm=algorithm)
            self.refuse(FIELDS, "Bearer " + token)

    def test_future_token(self):
        token = jwt.encode({"payload": FIELDS, "exp": int(time.time()) + 600, "nbf": int(time.time()) + 300}, SECRET)
        self.refuse(FIELDS, "Bearer " + token)

    def test_expired_body_with_valid_header(self):
        body, _ = signed(FIELDS, lifetime=-120)
        _, header = signed(FIELDS)
        self.assertTrue(self.refuse(body, header).expired)

    def test_missing_secret(self):
        for secret in (None, ""):
            with self.assertRaises(SERVICE.EditingCallbackRefused):
                SERVICE.verify_callback(*signed(FIELDS), secret)

    def test_ssrf_origins_and_ambiguous_urls(self):
        for url in (
            "http://169.254.169.254/latest/meta-data/",
            "http://documentserver.attacker.example/cache/file",
            "http://documentserver@attacker.example/cache/file",
            "http://user:password@documentserver/cache/file",
            "http://documentserver\\@attacker.example/cache/file",
            "http://documentserver:81/cache/file",
            "https://documentserver/cache/file",
            "http://documentserver\r\nHost: attacker.example/cache/file",
            "http://%64ocumentserver/cache/file",
        ):
            with self.subTest(url=url):
                self.assertFalse(URLS.is_editing_service_url(url, "http://documentserver"))

    def test_public_origin_rewrite_preserves_encoded_path_and_query(self):
        with patch.dict(
            os.environ,
            {"ONLYOFFICE_INTERNAL_URL": "http://documentserver", "ONLYOFFICE_PUBLIC_URL": "https://docs.example"},
        ):
            self.assertEqual(
                URLS.internal_saved_document_url("https://docs.example/cache/a%2Fb.docx?md5=a%2Bb&expires=10"),
                "http://documentserver/cache/a%2Fb.docx?md5=a%2Bb&expires=10",
            )

    def test_callback_url_redacted_outside_request_context(self):
        reference = "https://odoo.example/medilab/laboratory-files/callback/private-capability"
        for text in (reference, quote(reference, safe="")):
            record = logging.LogRecord("upstream.watchdog", logging.ERROR, __file__, 1, "failure %s", (text,), None)
            self.assertTrue(LOGGING.EditingCallbackFilter().filter(record))
            self.assertNotIn("private-capability", record.getMessage())

    def test_exception_chain_redacted(self):
        error = ValueError("/medilab/laboratory-files/callback/private-capability")
        record = logging.LogRecord(
            "upstream.watchdog", logging.ERROR, __file__, 1, "failed", (), (ValueError, error, None)
        )
        LOGGING.EditingCallbackFilter().filter(record)
        self.assertIsNone(record.exc_info)

    def test_double_encoded_callback_reference_is_redacted(self):
        capability = secrets.token_urlsafe(32)
        reference = "https://odoo.example/medilab/laboratory-files/callback/" + capability
        encoded = quote(quote(reference, safe=""), safe="")
        record = logging.LogRecord("upstream.watchdog", logging.ERROR, __file__, 1, "failure %s", (encoded,), None)
        LOGGING.EditingCallbackFilter().filter(record)
        self.assertTrue(capability not in record.getMessage(), "Callback diagnostic retained a capability")

    def test_raw_encoded_and_malformed_urls_do_not_print_capabilities(self):
        capability = secrets.token_urlsafe(32)
        reference = "https://odoo.example/medilab/laboratory-files/callback/" + capability
        variants = (
            reference,
            quote(reference, safe=""),
            quote(quote(reference, safe=""), safe=""),
            reference + "%ZZ%2",
            quote(reference, safe="").replace("%2F", "%2f") + "%FF%",
        )
        for index, value in enumerate(variants):
            with self.subTest(variant=index):
                record = logging.LogRecord("watchdog", logging.ERROR, __file__, 1, "%s", (value,), None)
                record.http_request_line = value
                LOGGING.EditingCallbackFilter().filter(record)
                self.assertTrue(
                    capability not in logging.Formatter().format(record), "Diagnostic retained a capability"
                )
                self.assertTrue(capability not in record.http_request_line, "Request line retained a capability")

    def test_trusted_incident_correlation_is_preserved(self):
        evidence = {"session_id": 7, "validated_save": True, "correlation": "agent4-correlation-7"}
        request = SimpleNamespace(httprequest=SimpleNamespace(environ={"medilab.editing_callback": evidence}))
        with patch.object(LOGGING, "request", request), self.assertLogs(LOGGING._logger.name, level="INFO") as messages:
            LOGGING.record_staged_document(7, "test-object", "a" * 64, 19)
        self.assertEqual(len(messages.records), 1)
        record = messages.records[0]
        LOGGING.EditingCallbackFilter().filter(record)
        self.assertIn("correlation_id=agent4-correlation-7", record.getMessage())
        self.assertIn("session_id=7", record.getMessage())

    def test_unrelated_diagnostics_preserved(self):
        record = logging.LogRecord("cleanup", logging.WARNING, __file__, 1, "cleanup object %s", ("object-7",), None)
        LOGGING.EditingCallbackFilter().filter(record)
        self.assertEqual(record.getMessage(), "cleanup object object-7")
