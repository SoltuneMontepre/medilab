from odoo import http

from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE, MODEL_SAMPLE_HANDOVER
from odoo.addons.sol_laboratory.services.laboratory_api import laboratory_api_route
from odoo.addons.sol_laboratory.services.mobile_documents import readable


class LaboratoryApiSamples(http.Controller):
    """Scanning a sample's label on Medilab Mobile: the sample as the person may see it, its receipt by their department,
    the testing tasks of their department they claim on it and the photos taken when it is collected or received."""

    @laboratory_api_route("/samples/lookup", ["GET"], "lookUpSample", permission=False)
    def look_up(self, device, _body, code):
        return device.env[MODEL_SAMPLE]._from_label(code)._mobile_detail()

    @laboratory_api_route("/samples/receive", ["POST"], "receiveSample", permission=False)
    def receive(self, device, body):
        handover = device.env[MODEL_SAMPLE_HANDOVER].receive_by_label(body["code"].strip())
        return handover.sample_id._mobile_detail()

    @laboratory_api_route("/samples/<int:sample_id>", ["GET"], "getSample", permission=False)
    def get_sample(self, device, _body, sample_id):
        return readable(device.env[MODEL_SAMPLE].browse(sample_id))._mobile_detail()

    @laboratory_api_route("/samples/<int:sample_id>/claim", ["POST"], "claimSampleTasks", permission=False)
    def claim(self, device, body, sample_id):
        sample = readable(device.env[MODEL_SAMPLE].browse(sample_id))
        sample._claim_from_phone(body["task_ids"])
        return sample._mobile_detail()

    @laboratory_api_route("/samples/<int:sample_id>/photos", ["GET"], "listSamplePhotos", permission=False)
    def list_photos(self, device, _body, sample_id):
        sample = readable(device.env[MODEL_SAMPLE].browse(sample_id))
        return {"photos": sample._mobile_photos()._mobile_values()}

    @laboratory_api_route("/samples/<int:sample_id>/photos", ["POST"], "attachSamplePhoto", permission=False)
    def attach_photo(self, device, body, sample_id, idempotency_key=None):
        sample = readable(device.env[MODEL_SAMPLE].browse(sample_id))
        return sample._attach_photo_from_phone(device, body, idempotency_key)._mobile_values()[0]
