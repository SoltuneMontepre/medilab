from odoo import http

from odoo.addons.sol_laboratory.constants.laboratory_files import FOLDER_READ
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER, MODEL_LABORATORY_UPLOAD
from odoo.addons.sol_laboratory.services.laboratory_api import api_datetime, json_answer, laboratory_api_route


class LaboratoryApiUploads(http.Controller):
    """Uploads of laboratory files: a computer prepares one, puts its parts straight into the bucket through presigned
    addresses, finalizes it, and reads it until the server has verified its content and stored its version. File bytes
    never pass through these routes."""

    @laboratory_api_route("/folders/<int:folder_id>/uploads", ["POST"], "prepareUpload")
    def prepare_upload(self, device, body, folder_id, idempotency_key):
        folder = device.env[MODEL_LABORATORY_FOLDER]._checked_for(folder_id, FOLDER_READ)
        upload = device.env[MODEL_LABORATORY_UPLOAD]._prepare(
            device,
            folder,
            body["path"],
            body["size"],
            body["sha256"],
            body.get("base_version_id"),
            idempotency_key,
        )
        return {"upload": upload._laboratory_api_values()}

    @laboratory_api_route("/folders/<int:folder_id>/uploads/<int:upload_id>", ["GET"], "getUpload")
    def get_upload(self, device, _body, folder_id, upload_id):
        upload = device.env[MODEL_LABORATORY_UPLOAD]._checked_for(device, folder_id, upload_id)
        return {"upload": upload._laboratory_api_values()}

    @laboratory_api_route("/folders/<int:folder_id>/uploads/<int:upload_id>/parts", ["POST"], "uploadParts")
    def upload_parts(self, device, body, folder_id, upload_id):
        upload = device.env[MODEL_LABORATORY_UPLOAD]._checked_for(device, folder_id, upload_id)
        addresses, expires_at = upload._part_addresses(body["part_numbers"])
        return {
            "parts": [{"number": number, "url": url} for number, url in addresses],
            "expires_at": api_datetime(expires_at),
        }

    @laboratory_api_route("/folders/<int:folder_id>/uploads/<int:upload_id>/finalize", ["POST"], "finalizeUpload")
    def finalize_upload(self, device, _body, folder_id, upload_id):
        upload = device.env[MODEL_LABORATORY_UPLOAD]._checked_for(device, folder_id, upload_id)
        upload._finalize()
        return json_answer({"upload": upload._laboratory_api_values()}, 202)
