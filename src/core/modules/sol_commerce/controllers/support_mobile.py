from odoo import http

from odoo.addons.sol_commerce.constants.models import MODEL_SUPPORT_REQUEST
from odoo.addons.sol_laboratory.services.laboratory_api import laboratory_api_route
from odoo.addons.sol_laboratory.services.mobile_documents import not_found


class SupportMobile(http.Controller):
    """The support requests sales handle on Medilab Mobile: listed, taken and answered as on the web."""

    @laboratory_api_route("/support-requests", ["GET"], "listSupportRequests", permission=False)
    def list_requests(self, device, _body, **query):
        # The list's name comes as the query parameter list, which a Python argument cannot be named.
        requests = device.env[MODEL_SUPPORT_REQUEST]._mobile_list(query["list"])
        return {"requests": requests._mobile_values()}

    @laboratory_api_route("/support-requests/<int:request_id>", ["GET"], "getSupportRequest", permission=False)
    def get_request(self, device, _body, request_id):
        return device.env[MODEL_SUPPORT_REQUEST]._mobile_readable(request_id)._mobile_detail()

    @laboratory_api_route("/support-requests/<int:request_id>/take", ["POST"], "takeSupportRequest", permission=False)
    def take(self, device, _body, request_id):
        # A request someone else took is no longer readable to the person: taking it says so.
        request = device.env[MODEL_SUPPORT_REQUEST].browse(request_id).exists()
        if not request:
            raise not_found(device.env)
        request._take_from_phone()
        return request._mobile_detail()

    @laboratory_api_route(
        "/support-requests/<int:request_id>/answer", ["POST"], "answerSupportRequest", permission=False
    )
    def answer(self, device, body, request_id, idempotency_key=None):
        request = device.env[MODEL_SUPPORT_REQUEST]._mobile_readable(request_id)
        request._answer_from_phone(device, body["body"], idempotency_key)
        return request._mobile_detail()
