from odoo import http

from odoo.addons.sol_laboratory.constants.medilab_mobile import HANDOVER_RECORD_PAGE_SIZE
from odoo.addons.sol_laboratory.constants.models import MODEL_HANDOVER_RECORD
from odoo.addons.sol_laboratory.services.laboratory_api import laboratory_api_route
from odoo.addons.sol_laboratory.services.mobile_documents import readable


class LaboratoryApiHandoverRecords(http.Controller):
    """Handover records on Medilab Mobile: the records the person may read and the customer's signature on one."""

    @laboratory_api_route("/handover-records", ["GET"], "listHandoverRecords", permission=False)
    def list_records(self, device, _body, status, after=None, limit=None):
        page_size = int(limit or HANDOVER_RECORD_PAGE_SIZE)
        offset = int(after or 0)
        records, more = device.env[MODEL_HANDOVER_RECORD]._mobile_page(status, offset, page_size)
        return {"records": records._mobile_values(), "next_after": offset + page_size if more else None}

    @laboratory_api_route("/handover-records/<int:record_id>", ["GET"], "getHandoverRecord", permission=False)
    def get_record(self, device, _body, record_id):
        return readable(device.env[MODEL_HANDOVER_RECORD].browse(record_id))._mobile_detail()

    @laboratory_api_route("/handover-records/<int:record_id>/sign", ["POST"], "signHandoverRecord", permission=False)
    def sign_record(self, device, body, record_id):
        record = readable(device.env[MODEL_HANDOVER_RECORD].browse(record_id))
        record._sign_from_phone(device, body)
        return record._mobile_detail()
