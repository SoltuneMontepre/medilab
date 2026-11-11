from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.sol_laboratory.constants.models import MODEL_SUBCONTRACT_DISPATCH
from odoo.addons.sol_laboratory.constants.routes import FRONTEND_PAGE
from odoo.addons.sol_laboratory.services.request_env import request_env

DISPATCH_COUNTER = "dispatch_count"
# The session key holding why the last result entered on a dispatch page was refused.
ERROR_KEY = "sol_laboratory_dispatch_error"


class MedilabDispatchPortal(CustomerPortal):
    """Subcontractors' people see the dispatches sent to their subcontractor and enter the results."""

    def _prepare_portal_counter_values(self, counter):
        if counter == DISPATCH_COUNTER:
            domain = request_env()[MODEL_SUBCONTRACT_DISPATCH]._portal_domain(request_env().user)
            return MODEL_SUBCONTRACT_DISPATCH, domain, "sudo"
        return super()._prepare_portal_counter_values(counter)

    @http.route("/my/dispatches", type="http", auth="user", **FRONTEND_PAGE)
    def portal_my_dispatches(self, **kwargs):
        values = self._prepare_portal_layout_values()
        values.update(page_name="dispatches", dispatches=self._dispatches())
        return request.render("sol_laboratory.portal_my_dispatches", values)

    @http.route("/my/dispatches/<int:dispatch_id>", type="http", auth="user", **FRONTEND_PAGE)
    def portal_my_dispatch(self, dispatch_id, **kwargs):
        dispatch = self._dispatches(dispatch_id)
        if not dispatch:
            return request.redirect("/my/dispatches")
        return self._render_dispatch(dispatch, error=request.session.pop(ERROR_KEY, None))

    @http.route("/my/dispatches/<int:dispatch_id>/results", type="http", auth="user", methods=["POST"], **FRONTEND_PAGE)
    def portal_enter_result(self, dispatch_id, sample_test_id="", value=None, value_text=None, **kwargs):
        dispatch = self._dispatches(dispatch_id)
        if not dispatch:
            return request.redirect("/my/dispatches")
        try:
            # A check after the result is written refuses it too, so the savepoint takes the result back.
            with request_env().cr.savepoint():
                dispatch._portal_enter_result(int(sample_test_id) if sample_test_id.isdigit() else 0, value, value_text)
        except UserError as error:
            # Kept in the session, not the address: the page shows only the system's own message.
            request.session[ERROR_KEY] = str(error)
        return request.redirect(f"/my/dispatches/{dispatch_id}")

    def _render_dispatch(self, dispatch, error=None):
        results = dispatch.sample_test_ids.result_ids.filtered(
            lambda result: result.is_reported and not result.is_replaced
        )
        values = self._prepare_portal_layout_values()
        values.update(
            page_name="dispatch",
            dispatch=dispatch,
            results={result.sample_test_id.id: result for result in results},
            rejections={
                result.sample_test_id.id: result._approval_rejection_reason()
                for result in results.filtered(lambda result: result.status == "rejected")
            },
            error=error,
        )
        return request.render("sol_laboratory.portal_my_dispatch", values)

    def _dispatches(self, dispatch_id=None):
        return request_env()[MODEL_SUBCONTRACT_DISPATCH]._portal_dispatches(request_env().user, dispatch_id)
