import logging
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote

from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.constants.laboratory_editing import CALLBACK_PREFIX
from odoo.addons.sol_laboratory.services import editing_callback_logging
from odoo.addons.sol_laboratory.services.editing_callback_logging import EditingCallbackFilter


@tagged("post_install", "-at_install")
class TestLaboratoryEditingLogging(TransactionCase):
    def test_nested_callback_paths_are_redacted_in_access_and_worker_records(self):
        url = "https://odoo.example" + CALLBACK_PREFIX + "secret-capability"
        for depth in range(20):
            for name in ("odoo.http.server", "odoo.tools.misc"):
                with self.subTest(depth=depth, logger=name):
                    record = logging.makeLogRecord({"name": name, "msg": "Thread (url:%s)", "args": (url,)})
                    record.http_request_line = "GET " + url + " HTTP/1.1"
                    with patch.object(editing_callback_logging, "request", None):
                        self.assertTrue(EditingCallbackFilter().filter(record))
                    self.assertNotIn("secret-capability", record.getMessage())
                    self.assertNotIn("secret-capability", record.http_request_line)
            url = quote(url, safe="")

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
        self.assertEqual(record.colored_message, record.getMessage())
        self.assertEqual(record.http_request_line, CALLBACK_PREFIX + "[redacted]")
        self.assertEqual(record.http_headers, ())
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
