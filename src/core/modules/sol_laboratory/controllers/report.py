from odoo import http

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ACTIONS_REPORT
from odoo.addons.sol_laboratory.services.request_env import request_env
from odoo.addons.web.controllers.report import ReportController

# The converters that make a file. An HTML report is shown in the browser.
DOWNLOAD_CONVERTERS = ("pdf", "text")


def _readonly_unless_downloaded(controller, rule, args):
    # Downloading writes an audit entry, which needs a read/write cursor.
    return args.get("converter") not in DOWNLOAD_CONVERTERS


class MedilabReport(ReportController):
    @http.route(readonly=_readonly_unless_downloaded)
    def report_routes(self, reportname, docids=None, converter=None, **data):
        response = super().report_routes(reportname, docids=docids, converter=converter, **data)
        if converter in DOWNLOAD_CONVERTERS and docids:
            report = request_env()[MODEL_IR_ACTIONS_REPORT]._get_report_from_name(reportname)
            report._audit_download([int(id_) for id_ in docids.split(",") if id_.isdigit()])
        return response
