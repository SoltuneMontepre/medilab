from odoo import http

from odoo.addons.sol_laboratory.services.laboratory_api import laboratory_api_route
from odoo.addons.sol_laboratory.services.mobile_documents import document_values


class LaboratoryApiDocuments(http.Controller):
    """The document a push, a notification or a task opens on Medilab Mobile, read with the person's rights."""

    @laboratory_api_route("/documents/<string:model>/<int:record_id>", ["GET"], "getDocument", permission=False)
    def get_document(self, device, _body, model, record_id):
        return document_values(device.env, model, record_id)
