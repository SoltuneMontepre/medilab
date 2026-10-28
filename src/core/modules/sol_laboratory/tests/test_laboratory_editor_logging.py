import io
import logging
import secrets
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote

from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.services.laboratory_editor_logging import LaboratoryEditorFilter, references_editor


@tagged("post_install", "-at_install")
class TestLaboratoryEditorLogging(TransactionCase):
    def record(self, name, text):
        return logging.LogRecord(name, logging.DEBUG, __file__, 1, "%s", (text,), None)

    def test_formatted_editor_diagnostics_are_redacted_and_emitted(self):
        self.longMessage = False
        capability = secrets.token_urlsafe(32)
        reference = quote(quote("/medilab/laboratory-files/17/edit?token=" + capability, safe=""), safe="")
        for field in ("msg", "http_request_line", "colored_message", "exc_text", "stack_info", "exc_info"):
            with self.subTest(field=field):
                record = self.record("odoo.tools.misc", "Transport failed")
                record.http_request_line = "GET /ordinary"
                record.colored_message = "Transport failed"
                record.http_headers = ("Authorization: Bearer " + capability,)
                if field == "msg":
                    record.args = (reference,)
                elif field == "exc_info":
                    error = ValueError(reference)
                    record.exc_info = (ValueError, error, None)
                else:
                    setattr(record, field, reference)
                record.http_response_status = 503
                output = io.StringIO()
                handler = logging.StreamHandler(output)
                handler.addFilter(LaboratoryEditorFilter())
                handler.setFormatter(
                    logging.Formatter("%(message)s %(http_request_line)s %(colored_message)s %(http_headers)s")
                )
                handler.handle(record)
                rendered = output.getvalue()
                self.assertIn("Laboratory editor HTTP status=503", rendered, "Sanitized security log was not emitted")
                self.assertNotIn(capability, rendered, "Editor diagnostic retained a credential")
                self.assertIsNone(record.exc_info)
                self.assertIsNone(record.exc_text)
                self.assertIsNone(record.stack_info)

    def test_unrelated_security_records_are_emitted_with_exception_and_attribution(self):
        error = ValueError("Object cleanup failed")
        record = self.record("odoo.addons.sol_laboratory.cleanup", "session_id=17 correlation_id=fixture-17")
        record.exc_info = (ValueError, error, None)
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        handler.addFilter(LaboratoryEditorFilter())
        handler.handle(record)
        self.assertIn("session_id=17 correlation_id=fixture-17", output.getvalue())
        self.assertIn("ValueError: Object cleanup failed", output.getvalue())

    def test_editor_references_keep_ascii_identifier_semantics(self):
        self.assertTrue(references_editor("/medilab/laboratory-files/17/edit?token=fixture"))
        self.assertTrue(references_editor("/medilab/laboratory-files/17/edit\u2003diagnostic"))
        for identifier in ("١٧", "１７", "1٧"):
            with self.subTest(identifier=identifier):
                self.assertFalse(references_editor(f"/medilab/laboratory-files/{identifier}/edit"))

    def test_named_filter_retains_logging_namespace_contract_after_redaction(self):
        filter_ = LaboratoryEditorFilter("odoo.http")
        for name, expected in (("odoo.http", True), ("odoo.http.server", True), ("odoo.https", False)):
            with self.subTest(name=name):
                record = self.record(name, "/medilab/laboratory-files/17/edit?token=private-value")
                self.assertEqual(filter_.filter(record), expected)
                self.assertNotIn("private-value", record.getMessage())
        self.assertTrue(LaboratoryEditorFilter().filter(self.record("security.audit", "session_id=17")))

    def test_nested_editor_references_are_redacted_outside_request_context(self):
        value = "/medilab/laboratory-files/17/edit?token=private-value"
        for _index in range(20):
            record = self.record("odoo.tools.misc", value)
            LaboratoryEditorFilter().filter(record)
            self.assertNotIn("private-value", record.getMessage())
            value = quote(value, safe="")

    def test_sdk_diagnostics_are_redacted_only_during_the_editor_request(self):
        record = self.record("botocore.auth", "X-Amz-Signature=private-value")
        with patch(
            "odoo.addons.sol_laboratory.services.laboratory_editor_logging.request",
            SimpleNamespace(httprequest=SimpleNamespace(path="/medilab/laboratory-files/17/edit")),
        ):
            LaboratoryEditorFilter().filter(record)
        self.assertNotIn("private-value", record.getMessage())
        unrelated = self.record("odoo.addons.sol_laboratory.cleanup", "Object cleanup evidence")
        LaboratoryEditorFilter().filter(unrelated)
        self.assertEqual(unrelated.getMessage(), "Object cleanup evidence")
