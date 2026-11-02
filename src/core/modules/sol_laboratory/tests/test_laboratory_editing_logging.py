import io
import logging
import sys
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote

from odoo.tests import TransactionCase, tagged

from .editing_service import callback
from odoo.addons.sol_laboratory.constants.laboratory_editing import CALLBACK_PREFIX
from odoo.addons.sol_laboratory.services import editing_callback_logging
from odoo.addons.sol_laboratory.services.editing_callback_logging import EditingCallbackFilter


@tagged("post_install", "-at_install")
class TestLaboratoryEditingLogging(TransactionCase):
    def test_named_filter_retains_logging_namespace_contract_after_redaction(self):
        filter_ = EditingCallbackFilter("odoo.http")
        for name, expected in (("odoo.http", True), ("odoo.http.server", True), ("odoo.https", False)):
            with self.subTest(name=name):
                record = logging.makeLogRecord({"name": name, "msg": CALLBACK_PREFIX + "private-capability"})
                with patch.object(editing_callback_logging, "request", None):
                    self.assertEqual(filter_.filter(record), expected)
                self.assertNotIn("private-capability", record.getMessage())

    def test_nested_callback_paths_are_redacted_in_access_and_worker_records(self):
        url = "https://odoo.example" + CALLBACK_PREFIX + "secret-capability"
        for depth in range(20):
            for name in ("odoo.http.server", "odoo.tools.misc"):
                with self.subTest(depth=depth, logger=name):
                    record = logging.makeLogRecord({"name": name, "msg": "Thread (url:%s)", "args": (url,)})
                    setattr(record, "http_request_line", "GET " + url + " HTTP/1.1")
                    with patch.object(editing_callback_logging, "request", None):
                        self.assertTrue(EditingCallbackFilter().filter(record))
                    self.assertNotIn("secret-capability", record.getMessage())
                    self.assertNotIn("secret-capability", getattr(record, "http_request_line"))
            url = quote(url, safe="")

    def _encoded_references(self):
        url = "https://odoo.example" + CALLBACK_PREFIX + "private-capability"
        encoded = quote(url, safe="")
        double = quote(encoded, safe="")
        return url, encoded, double, double.replace("%253A", "%253a").replace("%252F", "%252f", 2)

    def _assert_redacted(self, record, credentials):
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        handler.addFilter(EditingCallbackFilter())
        handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s %(colored_message)s"))
        with patch.object(editing_callback_logging, "request", None):
            handler.handle(record)
            first = vars(record).copy()
            handler.handle(record)
        self.assertEqual(vars(record), first)
        rendered = output.getvalue() + logging.Formatter().format(record) + repr(vars(record))
        for credential in credentials:
            self.assertFalse(credential in rendered, "A credential survived callback diagnostic redaction.")
        self.assertIn(record.name, output.getvalue())
        self.assertIn(record.levelname, output.getvalue())
        self.assertIn("HTTP status=403", output.getvalue())
        self.assertIsNone(record.exc_info)
        self.assertIsNone(record.exc_text)
        self.assertIsNone(record.stack_info)

    def test_double_encoded_callback_reference_is_redacted(self):
        reference = "https://odoo.example/medilab/laboratory-files/callback/private-capability"
        encoded = quote(quote(reference, safe=""), safe="")
        record = logging.LogRecord("upstream.watchdog", logging.ERROR, __file__, 1, "failure %s", (encoded,), None)
        with patch.object(editing_callback_logging, "request", None):
            EditingCallbackFilter().filter(record)
        self.assertFalse("private-capability" in record.getMessage(), "A double-encoded capability was logged.")

    def test_encoded_credentials_are_removed_from_every_formatted_boundary(self):
        presigned = "https://bucket.example/output?X-Amz-Credential=private-access&X-Amz-Signature=private-signature"
        body, header = callback({"key": "logging-test", "status": 2, "url": presigned})
        credentials = ("private-capability", "private-access", "private-signature", body["token"], header)
        for encoding, reference in enumerate(self._encoded_references()):
            diagnostic = f"{reference} {presigned} {body['token']} {header}"
            for boundary in (
                "msg",
                "args",
                "http_request_line",
                "colored_message",
                "exc_text",
                "stack_info",
                "exc_info",
            ):
                with self.subTest(boundary=boundary, encoding=encoding):
                    values = {
                        "name": "odoo.service.server",
                        "levelno": logging.ERROR,
                        "levelname": "ERROR",
                        "msg": "Worker failed",
                        "args": (),
                        "http_response_status": 403,
                        "http_headers": (("Medilab-Editor-Token", header),),
                    }
                    if boundary == "args":
                        values.update(msg="Thread (url:%s)", args=(diagnostic,))
                    elif boundary == "exc_info":
                        values[boundary] = (RuntimeError, RuntimeError(diagnostic), None)
                    else:
                        values[boundary] = diagnostic
                    self._assert_redacted(logging.makeLogRecord(values), credentials)

    def _raise_background_error(self, reference):
        raise RuntimeError("Background worker failed") from ValueError(reference)

    def test_chained_exceptions_and_traceback_caches_are_redacted(self):
        for reference in self._encoded_references():
            try:
                self._raise_background_error(reference)
            except RuntimeError:
                info = sys.exc_info()
                for cached in (False, True):
                    with self.subTest(cached=cached):
                        record = logging.makeLogRecord(
                            {
                                "name": "background",
                                "msg": "Worker failed",
                                "exc_info": info,
                                "http_response_status": 403,
                            }
                        )
                        if cached:
                            logging.Formatter().format(record)
                            record.exc_info = None
                        self._assert_redacted(record, ("private-capability",))
            else:
                raise AssertionError("The background error fixture must raise.")

    def test_normalization_has_strict_size_and_depth_limits(self):
        limit = editing_callback_logging.MAX_LOG_TEXT_LENGTH
        passes = editing_callback_logging.MAX_LOG_URL_DECODE_PASSES
        reference = self._encoded_references()[0]
        for _depth in range(passes + 5):
            reference = quote(reference, safe="")
        for diagnostic in ("x" * limit + self._encoded_references()[0], reference):
            with patch.object(editing_callback_logging, "unquote", wraps=editing_callback_logging.unquote) as decode:
                self.assertTrue(editing_callback_logging._may_reference_callback(diagnostic))
                self.assertLessEqual(decode.call_count, passes)
                for call in decode.call_args_list:
                    self.assertLessEqual(len(call.args[0]), limit)
            record = logging.makeLogRecord({"msg": diagnostic, "name": "watchdog", "http_response_status": 403})
            self._assert_redacted(record, ("private-capability",))

    def test_unrelated_encoded_diagnostics_and_recovery_metadata_are_preserved(self):
        messages = (
            "cleanup object object-7",
            quote(quote("https://example.test/health", safe=""), safe=""),
            "progress 50% malformed %zz literal %25",
            (
                "ONLYOFFICE callback status=503 outcome=concurrency_failure session_id=7 elapsed_seconds=1.250 "
                "correlation_id=0123456789abcdef error_type=ConcurrencyError"
            ),
            (
                "ONLYOFFICE callback staged_bytes session_id=7 object_key=0123456789abcdef "
                "sha256=abcdef size=42 correlation_id=0123456789abcdef"
            ),
        )
        for message in messages:
            record = logging.makeLogRecord({"name": "business", "msg": message})
            original = vars(record).copy()
            with patch.object(editing_callback_logging, "request", None):
                self.assertTrue(EditingCallbackFilter().filter(record))
            self.assertEqual(vars(record), original)

    def test_debug_access_records_redact_every_expanded_representation(self):
        record = logging.makeLogRecord(
            {
                "msg": "GET %s",
                "args": (CALLBACK_PREFIX + "secret-capability",),
                "http_request_line": "POST " + CALLBACK_PREFIX + "secret-capability HTTP/1.1",
                "http_headers": (("Medilab-Editor-Token", "secret-jwt"),),
                "colored_message": "secret-capability secret-jwt",
                "http_response_status": 403,
                "exc_text": "secret-capability",
                "stack_info": "secret-jwt",
            }
        )
        self.assertTrue(EditingCallbackFilter().filter(record))
        self.assertEqual(record.getMessage(), "ONLYOFFICE callback HTTP status=403")
        self.assertEqual(getattr(record, "colored_message"), record.getMessage())
        self.assertEqual(getattr(record, "http_request_line"), CALLBACK_PREFIX + "[redacted]")
        self.assertEqual(getattr(record, "http_headers"), ())
        self.assertIsNone(record.exc_text)
        self.assertIsNone(record.stack_info)

    def test_unrelated_http_records_keep_their_diagnostics(self):
        record = logging.makeLogRecord({"msg": "GET /web/health", "args": ()})
        self.assertTrue(EditingCallbackFilter().filter(record))
        self.assertEqual(record.getMessage(), "GET /web/health")

    def test_encoded_callback_paths_are_redacted_after_the_request_context_is_gone(self):
        line = "POST " + CALLBACK_PREFIX.replace("/", "%2F") + "secret-capability HTTP/1.1"
        record = logging.makeLogRecord({"msg": line, "args": (), "http_request_line": line})
        self.assertTrue(EditingCallbackFilter().filter(record))
        self.assertNotIn("secret-capability", record.getMessage())

    def test_scoped_network_redaction_preserves_business_cleanup_diagnostics(self):
        callback = SimpleNamespace(httprequest=SimpleNamespace(path=CALLBACK_PREFIX + "secret-capability"))
        transport = logging.makeLogRecord(
            {
                "name": "botocore.endpoint",
                "msg": "presigned-query secret-jwt",
                "args": (),
                "exc_text": "presigned-query",
            }
        )
        cleanup = logging.makeLogRecord(
            {
                "name": "odoo.addons.sol_laboratory.models.laboratory_files.laboratory_content",
                "msg": "Object cleanup needs reconciliation",
                "args": (),
            }
        )
        with patch.object(editing_callback_logging, "request", callback):
            self.assertTrue(EditingCallbackFilter().filter(transport))
            self.assertTrue(EditingCallbackFilter().filter(cleanup))
        self.assertNotIn("secret-jwt", transport.getMessage())
        self.assertIsNone(transport.exc_text)
        self.assertEqual(cleanup.getMessage(), "Object cleanup needs reconciliation")

    def test_worker_diagnostics_redact_callback_references_without_a_request_context(self):
        url = "https://odoo.example" + CALLBACK_PREFIX + "secret-capability"
        for name, encoded in (("odoo.tools.misc", url), ("odoo.service.server", url.replace("/", "%2F"))):
            with self.subTest(logger=name):
                record = logging.makeLogRecord({"name": name, "msg": "Thread (url:%s)", "args": (encoded,)})
                with patch.object(editing_callback_logging, "request", None):
                    self.assertTrue(EditingCallbackFilter().filter(record))
                self.assertNotIn("secret-capability", record.getMessage())

    def test_background_exception_redacts_callback_references_from_its_traceback(self):
        error = RuntimeError("Request failed at https://odoo.example" + CALLBACK_PREFIX + "secret-capability")
        record = logging.makeLogRecord(
            {"name": "odoo.service.server", "msg": "Worker failed", "args": (), "exc_info": (RuntimeError, error, None)}
        )
        with patch.object(editing_callback_logging, "request", None):
            self.assertTrue(EditingCallbackFilter().filter(record))
        self.assertIsNone(record.exc_info)
        self.assertNotIn("secret-capability", logging.Formatter().format(record))
