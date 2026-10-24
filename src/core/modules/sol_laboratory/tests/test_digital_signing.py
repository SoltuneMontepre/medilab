from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .signing_case import CREDENTIAL, SigningCase, self_signed
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY, MODEL_JOB_ITEM, MODEL_SIGNING_CERTIFICATE
from odoo.addons.sol_laboratory.constants.settings import DIGITAL_SIGNING_PARAMETER
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REPORT_REPORT
from odoo.addons.sol_laboratory.services.pdf_signing import check_pdf

ISSUED_EVENT = "sol_laboratory.event_test_report_issued"
SIGNING_JOB = "sol_laboratory.scheduled_job_digital_signing_sign"


@tagged("post_install", "-at_install")
class TestDigitalSigning(SigningCase):
    def print_pdf(self, report, person=None):
        printing = self.env["ir.actions.report"]
        if person:
            printing = self.as_person(printing, person)
        return printing._render_qweb_pdf(TEST_REPORT_REPORT, report.ids)[0]

    def html(self, report):
        return self.env["ir.actions.report"]._render_qweb_html(TEST_REPORT_REPORT, report.ids)[0].decode()

    def issued_messages(self, report):
        return self.env["mail.message"].search(
            [
                ("model", "=", report._name),
                ("res_id", "=", report.id),
                ("subtype_id", "=", self.env.ref(ISSUED_EVENT).id),
            ]
        )

    def signing_items(self, report):
        return self.env[MODEL_JOB_ITEM].search(
            [
                ("job_id", "=", self.env.ref(SIGNING_JOB).id),
                ("document_model", "=", report._name),
                ("document_id", "=", report.id),
            ]
        )

    def test_issuing_a_report_stores_the_pdf_viettel_sign_signed_with_the_laboratory_certificate(self):
        report = self.issue()

        signature = self.digital_signature(report)
        self.assertEqual(report.attachment_id, signature.attachment_id)
        self.assertEqual(report.attachment_id.name, f"{report.code}.pdf")
        self.assertEqual(signature.certificate_id.credential_id, CREDENTIAL)
        self.assertEqual(signature.document_version, report.document_version)
        check = check_pdf(bytes(report.attachment_id.raw))
        if check is None:
            self.fail("The stored PDF carries no digital signature.")
        self.assertTrue(check.signature_valid and check.whole_file)
        self.assertEqual(check.certificate, self.der)
        self.assertEqual(self.viettel.signings()[0][1]["credentialID"], CREDENTIAL)
        self.assertEqual(report.digital_signature_id, signature)
        self.assertEqual(report.digital_signed_at, signature.signed_at)
        self.assertFalse(report.digital_signing_pending)
        self.assertEqual(len(self.issued_messages(report)), 1)
        entries = self.env[MODEL_AUDIT_ENTRY].search(
            [("document_model", "=", report._name), ("document_id", "=", report.id), ("action", "=", "integration")]
        )
        self.assertIn(signature.certificate_id.name, entries.note)

    def test_signed_timestamp_tracks_signature_state_and_related_updates(self):
        self.complete()
        report = self.report()
        self.assertFalse(report.digital_signature_id)
        self.assertFalse(report.digital_signed_at)
        self.assertIn(report, self.env[report._name].search([("digital_signature_id", "=", False)]))

        self.sign(report)
        self.print_pdf(report)
        report.invalidate_recordset(["digital_signature_id", "digital_signed_at"])
        signature = report.digital_signature_id
        self.assertTrue(signature)
        self.assertEqual(report.digital_signed_at, signature.signed_at)
        self.assertEqual(self.env[report._name].search([("digital_signature_id", "=", signature.id)]), report)

        changed_at = fields.Datetime.subtract(signature.signed_at, minutes=1)
        signature.sudo().write({"signed_at": changed_at})

        self.assertEqual(report.digital_signed_at, changed_at)
        self.assertEqual(signature.document_version, report.document_version)

    def test_printing_a_fully_signed_report_returns_its_signed_pdf_every_time_without_an_extra_step(self):
        report = self.issue()

        first = self.print_pdf(report, self.courier)
        second = self.print_pdf(report, self.courier)

        self.assertEqual(first, bytes(report.attachment_id.raw))
        self.assertEqual(second, first)
        self.assertEqual(len(self.viettel.signings()), 1)

    def test_a_report_under_approval_prints_as_an_unsigned_marked_draft(self):
        self.complete()
        report = self.report()

        pdf = self.print_pdf(report, self.lab_head)

        self.assertIsNone(check_pdf(pdf))
        self.assertIn("Draft, not digitally signed", self.html(report))
        self.assertFalse(self.digital_signature(report))
        self.assertFalse(self.viettel.signings())

    def test_a_signed_report_prints_the_verification_address_and_no_draft_mark(self):
        report = self.issue()

        printed = self.html(report)

        self.assertNotIn("Draft, not digitally signed", printed)
        self.assertIn(f"{report.get_base_url()}/verify", printed)

    def test_without_digital_signing_an_issued_report_keeps_an_unsigned_pdf_without_the_draft_mark(self):
        self.env["ir.config_parameter"].set_bool(DIGITAL_SIGNING_PARAMETER, False)

        report = self.issue()

        self.assertTrue(report.attachment_id)
        self.assertIsNone(check_pdf(bytes(report.attachment_id.raw)))
        self.assertFalse(self.digital_signature(report))
        self.assertFalse(report.digital_signing_pending)
        printed = self.html(report)
        self.assertNotIn("Draft, not digitally signed", printed)
        self.assertNotIn("/verify", printed)
        self.assertEqual(len(self.issued_messages(report)), 1)

    def test_a_report_issued_before_digital_signing_was_on_is_signed_the_first_time_it_is_printed(self):
        self.env["ir.config_parameter"].set_bool(DIGITAL_SIGNING_PARAMETER, False)
        report = self.issue()
        self.env["ir.config_parameter"].set_bool(DIGITAL_SIGNING_PARAMETER, True)
        report.invalidate_recordset()

        self.assertFalse(report.digital_signing_pending)
        pdf = self.print_pdf(report, self.courier)

        check = check_pdf(pdf)
        self.assertTrue(check and check.signature_valid)
        self.assertEqual(report.attachment_id, self.digital_signature(report).attachment_id)
        self.assertEqual(len(self.issued_messages(report)), 1)

    def test_a_provider_outage_leaves_the_report_unsigned_and_the_job_signs_it_later(self):
        self.viettel.down = True

        report = self.issue()

        self.assertEqual(report.status, "issued")
        self.assertFalse(report.attachment_id)
        self.assertTrue(report.digital_signing_pending)
        self.assertFalse(self.digital_signature(report))
        self.assertFalse(self.issued_messages(report))
        self.assertEqual(self.signing_items(report).status, "pending")
        self.assertNotIn(report, self.waiting_for("to_deliver"))
        with self.assertRaises(UserError):
            self.as_person(report, self.courier).action_record_delivery()
        with self.assertRaises(UserError):
            self.print_pdf(report, self.courier)

        self.viettel.down = False
        self.env.ref(SIGNING_JOB)._run_batch()

        self.assertEqual(self.signing_items(report).status, "done")
        self.assertEqual(report.attachment_id, self.digital_signature(report).attachment_id)
        self.assertFalse(report.digital_signing_pending)
        self.assertEqual(len(self.issued_messages(report)), 1)
        self.assertIn(report, self.waiting_for("to_deliver"))

    def test_a_signature_the_certificate_does_not_verify_is_not_stored(self):
        self.viettel.signing_key, _der = self_signed("Someone Else", 365)

        report = self.issue()

        self.assertFalse(self.digital_signature(report))
        self.assertFalse(report.attachment_id)
        self.assertTrue(report.digital_signing_pending)
        self.assertEqual(self.signing_items(report).status, "pending")

    def test_the_signing_job_retries_while_viettel_sign_is_down(self):
        self.viettel.down = True
        report = self.issue()

        self.env.ref(SIGNING_JOB)._run_batch()

        item = self.signing_items(report)
        self.assertEqual((item.status, item.attempts), ("pending", 1))
        self.assertIn("could not be reached", item.last_error)
        self.assertTrue(report.digital_signing_pending)

    def test_a_person_retries_the_signing_by_hand(self):
        self.viettel.down = True
        report = self.issue()
        retry = self.as_person(report, self.courier).action_retry_digital_signing

        with self.assertRaises(UserError):
            retry()
        self.viettel.down = False
        retry()

        self.assertTrue(self.digital_signature(report))
        self.assertTrue(report.attachment_id)
        with self.assertRaises(UserError):
            retry()

    def test_an_expired_certificate_stops_digital_signing(self):
        self.complete()
        certificates = self.env[MODEL_SIGNING_CERTIFICATE]
        certificates._refresh()
        certificates.search([]).write({"status": "expired"})

        report = self.report()
        self.sign(report)

        self.assertTrue(report.digital_signing_pending)
        self.assertFalse(self.viettel.signings())
