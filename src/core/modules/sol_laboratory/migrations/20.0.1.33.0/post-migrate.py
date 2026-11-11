import hashlib

from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REPORT, MODEL_TEST_REPORT_CANDIDATE
from odoo.addons.sol_laboratory.constants.report_templates import CANDIDATE_ISSUED, CANDIDATE_MIGRATED


def migrate(cr, _version):
    # Reports issued before report templates keep their PDF as it is: each becomes an issued candidate of its own,
    # with the PDF's hash and no template or DOCX, and the PDF itself is neither rendered again nor changed.
    env = api.Environment(cr, SUPERUSER_ID, {})
    reports = env[MODEL_TEST_REPORT].search(
        [("status", "in", ("issued", "replaced")), ("attachment_id", "!=", False), ("candidate_ids", "=", False)]
    )
    env[MODEL_TEST_REPORT_CANDIDATE].create(
        [
            {
                "report_id": report.id,
                "origin": CANDIDATE_MIGRATED,
                "status": CANDIDATE_ISSUED,
                "attachment_id": report.attachment_id.id,
                "sha256": hashlib.sha256(bytes(report.attachment_id.raw or b"")).hexdigest(),
                "report_number": report.code,
                "report_date": report.issued_at and report._laboratory_day(report.issued_at),
            }
            for report in reports
        ]
    )
