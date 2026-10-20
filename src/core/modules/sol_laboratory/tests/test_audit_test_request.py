from odoo.tests import tagged

from .audit_case import AuditLookup
from .request_case import RequestCase


@tagged("post_install", "-at_install")
class TestAuditTestRequest(AuditLookup, RequestCase):
    def test_the_history_of_a_test_request_shows_the_changes_to_its_samples_and_sample_tests(self):
        auditor = self.new_auditor()
        sample_test = self.sample.test_ids
        other = self.create_request()
        self.sample.note = "Kept at 4 °C"
        sample_test.quantity = 2
        other.sample_ids.note = "Kept at room temperature"

        history = self.history(self.request, auditor)

        self.assertEqual(history, self.entries(self.request) | self.entries(self.sample) | self.entries(sample_test))
        self.assertEqual(self.changes(self.entries(self.sample, "edit")), {"note": (False, "Kept at 4 °C")})
        self.assertEqual(self.changes(self.entries(sample_test, "edit")), {"quantity": ("1", "2")})
        self.assertFalse(history & self.entries(other.sample_ids))
