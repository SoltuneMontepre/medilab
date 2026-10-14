from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ACTIONS_REPORT


class MedilabPortal(CustomerPortal):
    def _show_report(self, model, report_type, report_ref, download=False):
        response = super()._show_report(model, report_type, report_ref, download=download)
        # A PDF opened or downloaded from the portal is a download. The HTML report is the page itself.
        if report_type == "pdf":
            request.env[MODEL_IR_ACTIONS_REPORT]._get_report(report_ref)._audit_download(model.ids)
        return response
