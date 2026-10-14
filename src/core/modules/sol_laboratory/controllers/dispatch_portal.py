from urllib.parse import quote

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.sol_laboratory.constants.models import MODEL_SUBCONTRACT_DISPATCH

DISPATCH_COUNTER = "dispatch_count"


class MedilabDispatchPortal(CustomerPortal):
    """Subcontractors' people see the dispatches sent to their subcontractor and enter the results."""

    def _prepare_portal_counter_values(self, counter):
        if counter == DISPATCH_COUNTER:
            domain = request.env[MODEL_SUBCONTRACT_DISPATCH]._portal_domain(request.env.user)
            return MODEL_SUBCONTRACT_DISPATCH, domain, "sudo"
        return super()._prepare_portal_counter_values(counter)

    @http.route("/my/dispatches", type="http", auth="user", website=True)
    def portal_my_dispatches(self, **kwargs):
        values = self._prepare_portal_layout_values()
        values.update(page_name="dispatches", dispatches=self._dispatches())
        return request.render("sol_laboratory.portal_my_dispatches", values)

    @http.route("/my/dispatches/<int:dispatch_id>", type="http", auth="user", website=True)
    def portal_my_dispatch(self, dispatch_id, error=None, **kwargs):
        dispatch = self._dispatches(dispatch_id)
        if not dispatch:
            return request.redirect("/my/dispatches")
        results = dispatch.sample_test_ids.result_ids.filtered(
            lambda result: result.is_reported and not result.is_replaced
        )
        values = self._prepare_portal_layout_values()
        values.update(
            page_name="dispatch",
            dispatch=dispatch,
            results={result.sample_test_id.id: result for result in results},
            error=error,
        )
        return request.render("sol_laboratory.portal_my_dispatch", values)

    @http.route("/my/dispatches/<int:dispatch_id>/results", type="http", auth="user", methods=["POST"], website=True)
    def portal_enter_result(self, dispatch_id, sample_test_id="", value=None, value_text=None, **kwargs):
        dispatch = self._dispatches(dispatch_id)
        if not dispatch:
            return request.redirect("/my/dispatches")
        page = f"/my/dispatches/{dispatch_id}"
        try:
            dispatch._portal_enter_result(int(sample_test_id) if sample_test_id.isdigit() else 0, value, value_text)
        except UserError as error:
            return request.redirect(f"{page}?error={quote(str(error))}")
        return request.redirect(page)

    def _dispatches(self, dispatch_id=None):
        return request.env[MODEL_SUBCONTRACT_DISPATCH]._portal_dispatches(request.env.user, dispatch_id)
