import hashlib

from odoo.exceptions import UserError
from odoo.tests import tagged

from .change_request_case import ChangeRequestCase
from .report_case import PDF
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_SIGNATURE,
    MODEL_TASK,
    MODEL_TEST_REPORT,
    MODEL_TEST_RESULT,
)
from odoo.addons.sol_laboratory.constants.report_templates import REVIEWED_CANDIDATE_CONTEXT
from odoo.addons.sol_laboratory.constants.settings import DIGITAL_SIGNING_PARAMETER

ISSUED_EVENT = "sol_laboratory.event_test_report_issued"


@tagged("post_install", "-at_install")
class TestTestReportIssuance(ChangeRequestCase):
    """The lab head signs the prepared PDF they reviewed, which is issued as it is with digital signing off; result
    corrections stop an unissued report's signing and replace an issued one."""

    def signature_of(self, report):
        return self.env[MODEL_SIGNATURE].search(
            [("document_model", "=", report._name), ("document_id", "=", report.id), ("withdrawn_at", "=", False)]
        )

    def signing_tasks(self, report, status="open"):
        return self.env[MODEL_TASK].search(
            [("document_model", "=", report._name), ("document_id", "=", report.id), ("status", "=", status)]
        )

    def issued_messages(self, report):
        return self.env["mail.message"].search(
            [
                ("model", "=", report._name),
                ("res_id", "=", report.id),
                ("subtype_id", "=", self.env.ref(ISSUED_EVENT).id),
            ]
        )

    def correct(self, correction, value=0.006):
        """Approve the correction of a result, then send and approve its new version with the value."""
        self.sign(correction)
        version = self.env[MODEL_TEST_RESULT].browse(correction.new_document_id)
        self.as_person(version, self.tester).value = value
        self.send(version)
        self.approve(version)
        return version

    def test_a_report_is_signed_only_once_its_pdf_is_prepared(self):
        self.complete()
        report = self.report()
        lab_head = self.as_person(report, self.lab_head)

        self.assertFalse(lab_head.approval_can_sign)
        with self.assertRaises(UserError):
            lab_head.action_sign()
        self.prepare(report)

        self.assertTrue(lab_head.approval_can_sign)

    def test_signing_issues_the_reviewed_pdf_as_it_is_under_its_reserved_number(self):
        self.complete()
        report = self.report()
        candidate = self.prepare(report)

        self.sign(report)

        self.assertEqual(report.status, "issued")
        self.assertEqual(report.code, candidate.report_number)
        self.assertEqual(bytes(report.attachment_id.raw), PDF)
        self.assertEqual(report.attachment_id.res_model, MODEL_TEST_REPORT)
        self.assertEqual(candidate.status, "issued")
        self.assertEqual(self.signature_of(report).document_hash, hashlib.sha256(PDF).hexdigest())
        self.assertEqual(len(self.issued_messages(report)), 1)

    def test_a_pdf_out_of_date_with_the_records_cannot_be_signed(self):
        self.complete()
        report = self.report()
        self.prepare(report)
        self.customer.name = "An Phu Water Joint Stock Company"

        with self.assertRaises(UserError):
            self.as_person(report, self.lab_head).action_sign()
        self.assertEqual(report.status, "draft")

    def test_a_signer_signs_only_the_pdf_they_reviewed(self):
        self.complete()
        report = self.report()
        reviewed = self.prepare(report)
        self.editor(report).action_reopen_draft()
        self.prepare(report)

        with self.assertRaises(UserError):
            self.as_person(report, self.lab_head).with_context(
                **{REVIEWED_CANDIDATE_CONTEXT: reviewed.id}
            ).action_sign()
        self.assertEqual(report.status, "draft")

    def test_correcting_a_result_of_a_report_waiting_for_signature_returns_it_to_draft(self):
        result = self.complete()
        report = self.report()
        candidate = self.prepare(report)
        old_task = self.signing_tasks(report)

        self.sign(self.raise_on(result))

        self.assertEqual(candidate.status, "obsolete")
        self.assertEqual(old_task.status, "cancelled")
        self.assertFalse(self.as_person(report, self.lab_head).approval_can_sign)
        version = self.env[MODEL_TEST_RESULT].search([("replaces_id", "=", result.id)])
        self.send(version)
        self.approve(version)

        self.assertEqual(len(self.signing_tasks(report)), 1)
        self.sign(report)
        self.assertEqual((report.status, report.result_ids), ("issued", version))

    def test_a_correction_of_an_issued_result_links_the_reports_change_request(self):
        arsenic = self.add_test()
        lead = self.complete()
        kept = self.complete(test=arsenic)
        self.sign()
        report = self.report()

        first = self.raise_on(lead)
        second = self.raise_on(kept, person=self.tester, change="Report arsenic with 3 decimals.")

        linked = first.report_change_request_id
        self.assertEqual((linked.document_model, linked.document_id), (MODEL_TEST_REPORT, report.id))
        self.assertEqual(second.report_change_request_id, linked)
        self.assertEqual(linked.result_change_request_ids, first | second)
        self.assertEqual(linked.requested_by_id, self.tester)
        with self.assertRaises(UserError):
            self.raise_on(report, person=self.courier)

    def test_the_replacement_waits_for_the_corrected_results_and_only_its_issue_replaces_the_report(self):
        portal = self.portal_user()
        lead = self.complete()
        self.sign()
        report = self.report()
        correction = self.raise_on(lead)
        report_change = correction.report_change_request_id

        self.sign(report_change)

        self.assertEqual((report_change.status, report.status), ("approved", "issued"))
        self.assertFalse(report_change.new_document_id)
        self.sign(correction)
        version = self.env[MODEL_TEST_RESULT].browse(correction.new_document_id)
        self.as_person(version, self.tester).value = 0.006
        self.send(version)
        self.assertEqual(report_change.status, "approved")
        self.approve(version)

        replacement = self.env[MODEL_TEST_REPORT].browse(report_change.new_document_id)
        self.assertEqual(report_change.status, "applied")
        self.assertEqual((replacement.replaces_id, replacement.status), (report, "draft"))
        self.assertEqual(len(self.signing_tasks(replacement)), 1)
        self.assertEqual(report.status, "issued")
        reports = self.env[MODEL_TEST_REPORT]
        self.assertEqual(reports.search(reports._portal_domain(portal)), report)

        self.sign(replacement)

        self.assertEqual((replacement.status, report.status), ("issued", "replaced"))
        self.assertEqual(reports.search(reports._portal_domain(portal)), replacement)
        self.assertEqual(len(self.issued_messages(replacement)), 1)
        self.assertTrue(report.attachment_id)

    def test_a_rejected_correction_no_longer_holds_back_the_replacement(self):
        lead = self.complete()
        self.sign()
        correction = self.raise_on(lead)
        report_change = correction.report_change_request_id
        self.sign(report_change)

        self.as_person(correction, self.lab_head).action_reject("The worksheet confirms a dilution of 5.")

        self.assertEqual(report_change.status, "applied")
        self.assertTrue(self.env[MODEL_TEST_REPORT].browse(report_change.new_document_id))

    def test_a_correction_while_the_replacement_waits_joins_its_change_request_and_gives_it_a_fresh_task(self):
        lead = self.complete()
        self.sign()
        report = self.report()
        report_change = self.raise_on(report, person=self.courier)
        self.sign(report_change)
        replacement = self.env[MODEL_TEST_REPORT].browse(report_change.new_document_id)
        self.prepare(replacement)

        correction = self.raise_on(lead)
        self.assertEqual(correction.report_change_request_id, report_change)
        version = self.correct(correction)

        self.assertEqual(len(self.signing_tasks(replacement)), 1)
        self.assertEqual(len(self.signing_tasks(replacement, "cancelled")), 1)
        # The editor rebuilds the draft from the corrected result before preparing its PDF again.
        self.editor(replacement).action_generate_draft()
        self.sign(replacement)
        self.assertEqual((replacement.status, replacement.result_ids, report.status), ("issued", version, "replaced"))

    def test_a_replacement_pending_digital_signing_does_not_replace_the_issued_report(self):
        portal = self.portal_user()
        self.complete()
        self.sign()
        report = self.report()
        change = self.raise_on(report, person=self.courier)
        self.sign(change)
        replacement = self.env[MODEL_TEST_REPORT].browse(change.new_document_id)
        # Viettel Sign has no account in tests, so its signing fails.
        self.env["ir.config_parameter"].set_bool(DIGITAL_SIGNING_PARAMETER, True)

        self.sign(replacement)

        self.assertEqual((replacement.status, report.status), ("pending_signing", "issued"))
        self.assertFalse(replacement.attachment_id)
        self.assertFalse(self.issued_messages(replacement))
        reports = self.env[MODEL_TEST_REPORT]
        self.assertEqual(reports.search(reports._portal_domain(portal)), report)
        self.assertNotIn(replacement, self.waiting_for("to_deliver"))
        self.assertNotIn(replacement, self.waiting_for("to_sign"))

    def test_a_rejected_replacement_gets_a_fresh_signing_task_once_its_results_are_approved_again(self):
        lead = self.complete()
        self.sign()
        report = self.report()
        change = self.raise_on(report, person=self.courier)
        self.sign(change)
        replacement = self.env[MODEL_TEST_REPORT].browse(change.new_document_id)

        self.as_person(replacement, self.lab_head).action_reject("Check the lead digestion blank.", lead)

        self.assertFalse(self.signing_tasks(replacement))
        self.test._testing_task().write({"assignee_id": self.tester.id, "status": "assigned"})
        self.send(lead)
        self.approve(lead)
        self.assertEqual(len(self.signing_tasks(replacement)), 1)
        self.sign(replacement)
        self.assertEqual((replacement.status, report.status), ("issued", "replaced"))
