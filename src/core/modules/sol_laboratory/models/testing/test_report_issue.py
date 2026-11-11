from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.approvals import (
    STATE_APPLIED,
    STATE_APPROVED,
    STATE_REJECTED,
    STATE_REQUESTED,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_CHANGE_REQUEST,
    MODEL_DIGITAL_SIGNATURE,
    MODEL_IR_ATTACHMENT,
    MODEL_TASK,
    MODEL_TEST_REPORT,
)
from odoo.addons.sol_laboratory.constants.report_templates import CANDIDATE_ISSUED, REVIEWED_CANDIDATE_CONTEXT
from odoo.addons.sol_laboratory.constants.tasks import REPORT_DRAFTED_TRIGGER
from odoo.addons.sol_laboratory.models.testing.test_report import ISSUED_STATUSES, SIGNING_ACTION

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_report as TestReportBase
else:
    TestReportBase = object

# The status of a report whose last level signed while its digitally signed PDF is not stored yet.
PENDING_SIGNING = "pending_signing"
# The statuses of a report not issued yet.
UNISSUED_STATUSES = ("draft", "signing", PENDING_SIGNING)


# Phiếu Kết Quả: the lab head signs its prepared PDF, which is stored, digitally signed when signing is on, before the
# report is issued; result corrections stop its signing or replace it.
class TestReport(models.Model, TestReportBase):
    _inherit = MODEL_TEST_REPORT

    @api.depends("document_version", "status")
    def _compute_digital_signature(self):
        super()._compute_digital_signature()
        for report in self:
            # Only an approved report waits for its signed PDF, also once its queued signing gave up; a signing queued
            # before an approval was withdrawn no longer waits.
            report.digital_signing_pending = report.status == PENDING_SIGNING

    def _approval_check_actor(self, rejecting=False):
        level = super()._approval_check_actor(rejecting)
        if not rejecting:
            self._check_signable_candidate()
        return level

    def _check_signable_candidate(self):
        """The prepared PDF the signer signs: the one they reviewed, still matching the report's sources."""
        candidate = self._candidate()
        if not candidate:
            raise UserError(self.env._("Prepare the report's PDF and review it before signing."))
        reviewed = self.env.context.get(REVIEWED_CANDIDATE_CONTEXT)
        if reviewed and reviewed != candidate.id:
            raise UserError(
                self.env._("A new PDF of the report was prepared since you opened it; review it before signing.")
            )
        if not candidate._is_current():
            raise UserError(
                self.env._(
                    "The prepared PDF no longer matches its template, its draft or the business records; reopen the "
                    "draft and prepare the PDF again."
                )
            )
        return candidate

    def _approval_document_hash(self):
        # A signature of the report binds the prepared PDF its signer reviewed.
        return self._candidate().sha256 or False

    def _approval_set_state(self, state):
        if state == STATE_APPROVED:
            self._release()
        elif state == STATE_REQUESTED:
            self.status = "signing"
        else:
            self.status = "draft"
        if state in (STATE_APPROVED, STATE_REJECTED):
            self.env[MODEL_TASK]._close_for_document(self, SIGNING_ACTION)

    def _release(self):
        """Store the signed PDF and issue the report: digitally signed first when digital signing is on, otherwise the
        prepared PDF as it is. While Viettel Sign fails the report waits pending digital signing, its approvals
        standing."""
        self.ensure_one()
        report = self.sudo()
        report.status = PENDING_SIGNING
        if report._digital_signing_enabled():
            report._digital_signing_start()
        else:
            report._issue_unsigned()

    def _issue_unsigned(self):
        report = self.sudo()
        report._issue(report._attach_pdf(bytes(report._issuable_candidate().attachment_id.raw)))

    def _issuable_candidate(self):
        """The prepared PDF to issue: the report's last level signed, every signature still stands and the PDF still
        matches its sources. A retry checks it again, so a withdrawn approval or a correction stops it."""
        self.ensure_one()
        report = self.sudo()
        candidate = report._candidate()
        if report.status != PENDING_SIGNING or not super()._digital_signing_fully_signed():
            raise UserError(self.env._("%s is not approved, so its PDF cannot be issued.", report.display_name))
        if not candidate or not candidate._is_current():
            raise UserError(
                self.env._(
                    "The prepared PDF of %s no longer matches its sources, so it cannot be issued.", report.display_name
                )
            )
        return candidate

    def _attach_pdf(self, pdf):
        return (
            self.env[MODEL_IR_ATTACHMENT]
            .sudo()
            .create(
                {
                    "name": self._digital_signing_filename(),
                    "raw": pdf,
                    "mimetype": "application/pdf",
                    "res_model": self._name,
                    "res_id": self.id,
                }
            )
        )

    def _issue(self, attachment):
        """Issue the report with its stored PDF: mark its prepared PDF issued, the report it replaces replaced and its
        request and samples reported, retain the kept samples and tell the customer, once."""
        self.ensure_one()
        report = self.sudo()
        if report.status in ISSUED_STATUSES:
            return
        candidate = report._candidate()
        report.write({"issued_at": fields.Datetime.now(), "status": "issued", "attachment_id": attachment.id})
        candidate.status = CANDIDATE_ISSUED
        report.replaces_id.status = "replaced"
        request = report.request_id
        reported = request.sample_ids.filtered(lambda sample: sample.status == "completed")
        reported.status = "reported"
        reported._retain(report._report_day())
        if request.status != "reported":
            request._set_status("reported")
        report._notify_issued()

    def _digital_signing_fully_signed(self):
        return self.status in (PENDING_SIGNING, *ISSUED_STATUSES)

    def _digital_signing_filename(self):
        return f"{self.code}.pdf"

    def _digital_signing_source(self):
        # Viettel Sign signs the PDF the lab head reviewed and signed, never a new rendering.
        return bytes(self._issuable_candidate().attachment_id.raw)

    def _digital_sign(self):
        # A report still pending once digital signing is turned off is issued with its prepared PDF as it is.
        if self.status == PENDING_SIGNING and not self._digital_signing_enabled():
            self._issue_unsigned()
            return self.env[MODEL_DIGITAL_SIGNATURE]
        return super()._digital_sign()

    def _digital_signing_done(self, signature):
        self._issue(signature.attachment_id)

    def _digital_signed_pdf(self):
        # An issued report prints its stored PDF, also one issued while digital signing was off.
        if self.sudo().status in ISSUED_STATUSES:
            return bytes(self.sudo().attachment_id.raw)
        return super()._digital_signed_pdf()

    def _change_request_ready(self, change_request):
        """True once the report's change request can create the replacement: no result correction linked to it waits
        for its chain, and every result the report prints is approved."""
        report = self.sudo()
        return not change_request.sudo().result_change_request_ids.filtered(
            lambda correction: correction.status == STATE_REQUESTED
        ) and all(result.status == STATE_APPROVED for result in report.result_ids)

    @api.model
    def _correction_request(self, result, requested_change, reason, person):
        """The change request of the issued report that prints the result, which a correction of the result joins:
        the report's open one, the one whose replacement is still unissued, or a new one; none when no issued report
        prints the result."""
        report = self.sudo().search(
            [("request_id", "=", result.sudo().sample_id.request_id.id), ("status", "=", "issued")]
        )
        if result not in report.result_ids:
            return self.env[MODEL_CHANGE_REQUEST]
        requests = self.env[MODEL_CHANGE_REQUEST].sudo()
        replacement = self.sudo().search([("replaces_id", "=", report.id)])
        if replacement:
            return requests.search(
                [
                    ("document_model", "=", self._name),
                    ("status", "=", STATE_APPLIED),
                    ("new_document_id", "=", replacement.id),
                ],
                limit=1,
            )
        return requests.search(
            [
                ("document_model", "=", self._name),
                ("document_id", "=", report.id),
                ("status", "in", (STATE_REQUESTED, STATE_APPROVED)),
            ],
            limit=1,
        ) or requests.create(
            {
                "document_model": self._name,
                "document_id": report.id,
                "requested_by_id": person.id,
                "requested_change": self.env._(
                    "Replace the report with the corrected result %(result)s: %(change)s",
                    result=result.sudo().display_name,
                    change=requested_change,
                ),
                "reason": reason,
            }
        )

    @api.model
    def _stop_signing(self, requests, reason):
        """A correction of a result stops the signing of its request's unissued report: its signatures are withdrawn,
        its prepared PDF becomes obsolete and its signing task is cancelled until the corrected results are approved."""
        for report in self.sudo().search([("request_id", "in", requests.ids), ("status", "in", UNISSUED_STATUSES)]):
            if report._approval_open_rows():
                report._approval_restart()
            report._candidate()._invalidate(reason)
            self.env[MODEL_TASK]._cancel_for_document(report, SIGNING_ACTION)

    @api.model
    def _follow_corrections(self, requests):
        """Once results of the requests are approved: create the replacements whose change requests waited for them,
        and give an unissued replacement whose results are all approved again a fresh signing task."""
        reports = self.sudo().search([("request_id", "in", requests.ids)])
        issued = reports.filtered(lambda report: report.status == "issued" and report._change_request_open())
        waiting = (
            self.env[MODEL_CHANGE_REQUEST]
            .sudo()
            .search(
                [
                    ("document_model", "=", self._name),
                    ("document_id", "in", issued.ids),
                    ("status", "=", STATE_APPROVED),
                ]
            )
        )
        for change_request in waiting:
            change_request._apply()
        tasks = self.env[MODEL_TASK]
        for report in reports.filtered(
            lambda report: bool(report.replaces_id) and report.status in ("draft", "signing")
        ):
            if tasks._system_tasks_of(report, SIGNING_ACTION) or any(
                result.status != STATE_APPROVED for result in report.result_ids
            ):
                continue
            # The lab head's rejection stays on record; the replacement is signed again from the first level.
            if report._approval_open_rows():
                report._approval_restart()
            tasks._create_for_event(REPORT_DRAFTED_TRIGGER, document=report)
