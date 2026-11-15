from odoo import http

from odoo.addons.sol_laboratory.constants.medilab_mobile import RESULT_PAGE_SIZE
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST, MODEL_TEST_RESULT
from odoo.addons.sol_laboratory.services.laboratory_api import laboratory_api_route
from odoo.addons.sol_laboratory.services.mobile_documents import readable


class LaboratoryApiResults(http.Controller):
    """Testing at the bench on Medilab Mobile: a sample test, entering and changing its result, sending or approving it,
    rejecting it, and the results waiting for the person's signature."""

    @laboratory_api_route("/sample-tests/<int:sample_test_id>", ["GET"], "getSampleTest", permission=False)
    def get_sample_test(self, device, _body, sample_test_id):
        return readable(device.env[MODEL_SAMPLE_TEST].browse(sample_test_id))._mobile_detail()

    @laboratory_api_route(
        "/sample-tests/<int:sample_test_id>/results", ["POST"], "enterSampleTestResult", permission=False
    )
    def enter_result(self, device, body, sample_test_id, idempotency_key=None):
        test = readable(device.env[MODEL_SAMPLE_TEST].browse(sample_test_id))
        return test._enter_from_phone(device, body, idempotency_key)._mobile_detail()

    @laboratory_api_route("/results", ["GET"], "listResults", permission=False)
    def list_results(self, device, _body, after=None, limit=None, **_awaiting):
        # The list is given by awaiting=me, the only list the route takes.
        page_size = int(limit or RESULT_PAGE_SIZE)
        offset = int(after or 0)
        results, more = device.env[MODEL_TEST_RESULT]._mobile_awaiting(offset, page_size)
        return {"results": results._mobile_values(), "next_after": offset + page_size if more else None}

    @laboratory_api_route("/results/<int:result_id>", ["GET"], "getResult", permission=False)
    def get_result(self, device, _body, result_id):
        return readable(device.env[MODEL_TEST_RESULT].browse(result_id))._mobile_detail()

    @laboratory_api_route("/results/<int:result_id>", ["PATCH"], "changeResult", permission=False)
    def change_result(self, device, body, result_id):
        result = readable(device.env[MODEL_TEST_RESULT].browse(result_id))
        result._change_from_phone(body)
        return result._mobile_detail()

    @laboratory_api_route("/results/<int:result_id>/sign", ["POST"], "signResult", permission=False)
    def sign_result(self, device, body, result_id):
        result = readable(device.env[MODEL_TEST_RESULT].browse(result_id))
        result._sign_from_phone(body)
        return result._mobile_detail()

    @laboratory_api_route("/results/<int:result_id>/reject", ["POST"], "rejectResult", permission=False)
    def reject_result(self, device, body, result_id):
        result = readable(device.env[MODEL_TEST_RESULT].browse(result_id))
        result.action_reject(body["reason"])
        return result._mobile_detail()
