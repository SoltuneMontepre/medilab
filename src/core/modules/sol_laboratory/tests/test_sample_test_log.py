from freezegun import freeze_time

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .audit_case import AuditLookup
from .result_case import ResultCase
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestSampleTestLog(AuditLookup, ResultCase):
    def test_whoever_reads_sample_tests_reads_the_log_of_the_test_its_bookings_and_its_results(self):
        self.grant(self.tester, "sample_test.read.all")
        booking = self.schedule(self.test, self.tester)
        result = self.enter()
        other = self.add_test()

        log = self.as_person(self.test, self.tester).log_ids

        self.assertEqual(log, self.entries(self.test) | self.entries(booking) | self.entries(result))
        self.assertFalse(log & self.entries(other))
        self.assertTrue(log.mapped("change_ids.display_name"))

    def test_the_audit_trail_stays_closed_to_whoever_cannot_read_sample_tests(self):
        outsider = self.create_person("Vo Thi Hoa", self.microbiology, "hoa.vo")

        with self.assertRaises(AccessError):
            self.env[MODEL_AUDIT_ENTRY].with_user(outsider.user_id).search([])

    def test_whoever_reads_sample_tests_reads_no_entry_about_other_documents(self):
        self.grant(self.tester, "sample_test.read.all")
        entries = self.env[MODEL_AUDIT_ENTRY].with_user(self.tester.user_id)

        self.assertFalse(entries.search([("document_model", "=", self.request._name)]))
