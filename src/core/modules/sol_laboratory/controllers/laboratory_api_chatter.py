from odoo import http

from odoo.addons.sol_laboratory.services.laboratory_api import laboratory_api_route
from odoo.addons.sol_laboratory.services.mobile_messages import chatter_document, message_page, post_from_phone


class LaboratoryApiChatter(http.Controller):
    """The chatter of a task, a sample or a test request on Medilab Mobile, read with the person's rights, and the notes
    the person posts on it, which never reach a customer."""

    @laboratory_api_route(
        "/documents/<string:model>/<int:record_id>/messages", ["GET"], "listDocumentMessages", permission=False
    )
    def list_messages(self, device, _body, model, record_id, before=None, limit=None):
        return message_page(chatter_document(device.env, model, record_id), before=before, limit=limit)

    @laboratory_api_route(
        "/documents/<string:model>/<int:record_id>/notes", ["POST"], "postDocumentNote", permission=False
    )
    def post_note(self, device, body, model, record_id, idempotency_key=None):
        document = chatter_document(device.env, model, record_id)
        note = post_from_phone(document, device, body, idempotency_key, subtype_xmlid="mail.mt_note")
        return note._mobile_values()[0]
