import hashlib
from pathlib import Path

from odoo import fields
from odoo.modules.module import load_script
from odoo.tests import tagged

from .report_case import PDF, ReportCase
from odoo.addons.sol_laboratory.constants.report_templates import CANDIDATE_ISSUED, CANDIDATE_MIGRATED

POST_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.28.0" / "post-migrate.py"


@tagged("post_install", "-at_install")
class TestReportCandidateMigration(ReportCase):
    def test_issued_pdf_becomes_an_issued_candidate_unchanged(self):
        self.complete()
        report = self.report()
        # A report issued before report templates: its PDF printed when it was issued, with no prepared candidate.
        attachment = self.env["ir.attachment"].create(
            {"name": "PKQ.2025.0001.pdf", "raw": PDF, "mimetype": "application/pdf", "res_model": report._name}
        )
        report.sudo().write(
            {
                "status": "issued",
                "code": "PKQ.2025.0001",
                "issued_at": fields.Datetime.now(),
                "attachment_id": attachment.id,
            }
        )
        pdf = bytes(attachment.raw)
        checksum = attachment.checksum

        load_script(str(POST_MIGRATE), "post_migrate").migrate(self.env.cr, "20.0.1.26.0")
        load_script(str(POST_MIGRATE), "post_migrate").migrate(self.env.cr, "20.0.1.26.0")

        self.env.invalidate_all()
        candidate = report.candidate_ids
        self.assertEqual(len(candidate), 1)
        self.assertEqual((candidate.origin, candidate.status), (CANDIDATE_MIGRATED, CANDIDATE_ISSUED))
        self.assertEqual(candidate.attachment_id, attachment)
        self.assertEqual(candidate.sha256, hashlib.sha256(pdf).hexdigest())
        self.assertEqual(candidate.report_number, report.code)
        self.assertFalse(candidate.template_version_id)
        self.assertEqual(report.attachment_id, attachment)
        self.assertEqual(attachment.checksum, checksum)
        self.assertEqual(bytes(attachment.raw), pdf)
