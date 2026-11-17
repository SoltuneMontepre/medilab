from odoo import http
from odoo.http import request
from odoo.http.stream import content_disposition

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ATTACHMENT
from odoo.addons.sol_laboratory.services.laboratory_api import laboratory_api_route
from odoo.addons.sol_laboratory.services.mobile_documents import not_found, readable


class LaboratoryApiAttachments(http.Controller):
    """A file Medilab Mobile shows, such as a sample's photo, downloaded with the person's rights, so a tester never
    downloads a sample photo."""

    @laboratory_api_route("/attachments/<int:attachment_id>", ["GET"], "downloadAttachment", permission=False)
    def download(self, device, _body, attachment_id):
        attachment = readable(device.env[MODEL_IR_ATTACHMENT].browse(attachment_id))
        if attachment.type != "binary":
            raise not_found(device.env)
        return request.make_response(
            bytes(attachment.raw or b""),
            headers=[
                ("Content-Type", attachment.mimetype or "application/octet-stream"),
                ("Content-Disposition", content_disposition(attachment.name or "file")),
                ("Cache-Control", "private, no-store"),
            ],
        )
