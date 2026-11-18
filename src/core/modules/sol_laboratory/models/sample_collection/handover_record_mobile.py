from typing import TYPE_CHECKING

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools.mimetypes import guess_mimetype

from odoo.addons.sol_laboratory.constants.laboratory_files import INVALID_REQUEST, PERMISSION_DENIED
from odoo.addons.sol_laboratory.constants.medilab_mobile import SIGNATURE_MAX_BYTES
from odoo.addons.sol_laboratory.constants.models import MODEL_HANDOVER_RECORD, MODEL_SAMPLE
from odoo.addons.sol_laboratory.services.laboratory_api import api_datetime
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.mobile_uploads import decoded_base64

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_handover_record as HandoverRecordMobileBase
else:
    HandoverRecordMobileBase = object


# Biên Bản Giao Nhận Mẫu: what Medilab Mobile reads of a handover record and the customer's signature it records, with
# the person's rights.
class HandoverRecordMobile(models.Model, HandoverRecordMobileBase):
    _name = MODEL_HANDOVER_RECORD
    _inherit = MODEL_HANDOVER_RECORD

    @api.model
    def _mobile_page(self, status, offset, limit):
        """A page of the records of the status the person may read, latest handover first, and whether another page
        follows."""
        records = self.search([("status", "=", status)], offset=offset, limit=limit + 1)
        return records[:limit], len(records) > limit

    def _mobile_values(self):
        """The records as Medilab Mobile lists them. The test request and the people are named as the web's list names
        them."""
        return [
            {
                "id": record.id,
                "code": record.code,
                "request": record.sudo().request_id.display_name or "",
                "handed_over_at": api_datetime(record.handed_over_at),
                "handed_over_by": record.handed_over_by_name,
                "status": record.status,
                "signed_at": api_datetime(record.signed_at),
            }
            for record in self
        ]

    def _mobile_detail(self):
        """The record with the samples it lists and what was handed over of each, the phone it was signed on and
        whether the person may have the customer sign it now."""
        self.ensure_one()
        customer_visible = self.env[MODEL_SAMPLE]._customer_visible()
        conditions = dict(self.sample_ids._fields["condition"]._description_selection(self.env))
        # The people are named as the web's form names them.
        named = self.sudo()
        return {
            **self._mobile_values()[0],
            "received_by": named.received_by_id.name or "",
            "signed_device": named.signed_device_id.name or "",
            "samples": [line._mobile_values(customer_visible, conditions) for line in self.sample_ids],
            "can_sign": self.status == "draft" and bool(self.sample_ids) and bool(self._filtered_access("write")),
        }

    def _sign_from_phone(self, device, values):
        """Record the customer's signature with the phone of the key as the device it was signed on. The record signed
        from this phone already answers as it is, so a signature sent again after a lost answer is not refused."""
        self.ensure_one()
        if self.status == "signed":
            if self.signed_device_id == device:
                return
            raise UserError(self.env._("Handover record %s is already signed.", self.code))
        if not self._filtered_access("write"):
            raise LaboratoryFileError(
                PERMISSION_DENIED, self.env._("You may not have handover record %s signed.", self.code)
            )
        self._sign(_decoded_signature(self.env, values["signature"]), device)


def _decoded_signature(env, data):
    """The PNG of the signature the phone sent in base64; one over the limit is refused before it is decoded."""
    signature = decoded_base64(
        data,
        SIGNATURE_MAX_BYTES,
        env._("A signature can be at most 1 MiB."),
        env._("The signature is not valid base64."),
    )
    if guess_mimetype(signature) != "image/png":
        raise LaboratoryFileError(INVALID_REQUEST, env._("The signature is not a PNG image."))
    return signature
