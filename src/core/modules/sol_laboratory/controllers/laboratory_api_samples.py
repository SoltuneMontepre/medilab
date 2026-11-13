from odoo import http

from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE, MODEL_SAMPLE_HANDOVER
from odoo.addons.sol_laboratory.services.laboratory_api import laboratory_api_route
from odoo.addons.sol_laboratory.services.mobile_documents import not_found


def readable_sample(env, sample_id):
    """The sample of the id once the person may read it; one they may not read is not found."""
    sample = env[MODEL_SAMPLE].browse(sample_id).exists()
    if not sample:
        raise not_found(env)
    sample.check_access("read")
    return sample


class LaboratoryApiSamples(http.Controller):
    """Scanning a sample's label on Medilab Mobile: the sample as the person may see it, its receipt by their department
    and the testing tasks of their department they claim on it."""

    @laboratory_api_route("/samples/lookup", ["GET"], "lookUpSample", permission=False)
    def look_up(self, device, _body, code):
        return device.env[MODEL_SAMPLE]._from_label(code)._mobile_detail()

    @laboratory_api_route("/samples/receive", ["POST"], "receiveSample", permission=False)
    def receive(self, device, body):
        handover = device.env[MODEL_SAMPLE_HANDOVER].receive_by_label(body["code"].strip())
        return handover.sample_id._mobile_detail()

    @laboratory_api_route("/samples/<int:sample_id>", ["GET"], "getSample", permission=False)
    def get_sample(self, device, _body, sample_id):
        return readable_sample(device.env, sample_id)._mobile_detail()

    @laboratory_api_route("/samples/<int:sample_id>/claim", ["POST"], "claimSampleTasks", permission=False)
    def claim(self, device, body, sample_id):
        sample = readable_sample(device.env, sample_id)
        sample._claim_from_phone(body["task_ids"])
        return sample._mobile_detail()
