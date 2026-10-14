from odoo import http
from odoo.fields import Domain
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REPORT

# The counter of the portal card that lists the customer's test reports.
REPORT_COUNTER = "test_report_count"


class MedilabTestReportPortal(CustomerPortal):
    """The customer downloads the issued test reports of their own requests."""

    def _prepare_portal_counter_values(self, counter):
        if counter == REPORT_COUNTER:
            return MODEL_TEST_REPORT, request.env[MODEL_TEST_REPORT]._portal_domain(request.env.user), "sudo"
        return super()._prepare_portal_counter_values(counter)

    @http.route("/my/test-reports", type="http", auth="user", website=True)
    def portal_test_reports(self, **kwargs):
        reports = request.env[MODEL_TEST_REPORT]
        values = self._prepare_portal_layout_values()
        values.update(
            page_name="test_reports",
            reports=reports.sudo().search(reports._portal_domain(request.env.user), order="issued_at desc, id desc"),
        )
        return request.render("sol_laboratory.portal_my_test_reports", values)

    @http.route("/my/test-reports/<int:report_id>/download", type="http", auth="user", website=True)
    def portal_test_report_download(self, report_id, **kwargs):
        # Another customer's report, or one not issued, is not found.
        reports = request.env[MODEL_TEST_REPORT]
        report = reports.sudo().search(Domain("id", "=", report_id) & reports._portal_domain(request.env.user), limit=1)
        if not report.attachment_id:
            return request.not_found()
        return request.env["ir.binary"]._get_stream_from(report.attachment_id).get_response(as_attachment=True)
