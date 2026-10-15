from odoo import api, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_TEST_REPORT,
    MODEL_TEST_REPORT_DOCUMENT,
    MODEL_TEST_RESULT,
)
from odoo.addons.sol_laboratory.models.testing.test_report import OPEN_STATUSES


# Bản In Phiếu Kết Quả
class TestReportDocument(models.AbstractModel):
    _name = MODEL_TEST_REPORT_DOCUMENT
    _description = "Test Report Document"

    @api.model
    def _get_report_values(self, docids, data=None):
        reports = self.env[MODEL_TEST_REPORT].browse(docids)
        # A report not issued yet prints results that are not released, so only those who read results print it.
        if any(report.status in OPEN_STATUSES for report in reports.sudo()):
            self.env[MODEL_TEST_RESULT].check_access("read")
        return {"doc_ids": docids, "doc_model": MODEL_TEST_REPORT, "docs": reports}
