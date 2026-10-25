import logging
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote

from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.services.laboratory_editor_logging import LaboratoryEditorFilter


@tagged("post_install", "-at_install")
class TestLaboratoryEditorLogging(TransactionCase):
    def record(self, name, text):
        return logging.LogRecord(name, logging.DEBUG, __file__, 1, "%s", (text,), None)

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
