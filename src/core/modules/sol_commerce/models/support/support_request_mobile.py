from typing import TYPE_CHECKING

from odoo import api, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import html2plaintext, plaintext2html

from odoo.addons.sol_commerce.constants.models import MODEL_SUPPORT_REQUEST
from odoo.addons.sol_commerce.constants.support import (
    COMMENT,
    SUPPORT_ANSWERED,
    SUPPORT_CLOSED,
    SUPPORT_MINE,
    SUPPORT_OPEN,
)
from odoo.addons.sol_laboratory.constants.laboratory_files import IDEMPOTENCY_CONFLICT, PERMISSION_DENIED
from odoo.addons.sol_laboratory.constants.medilab_mobile import ALREADY_TAKEN
from odoo.addons.sol_laboratory.constants.models import MODEL_MAIL_MESSAGE
from odoo.addons.sol_laboratory.services.laboratory_api import api_datetime
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.mobile_documents import not_found

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_support_request as SupportRequestMobileBase
else:
    SupportRequestMobileBase = object


# Yêu Cầu Hỗ Trợ: what Medilab Mobile reads and does with support requests, with the person's rights.
class SupportRequestMobile(models.Model, SupportRequestMobileBase):
    _inherit = MODEL_SUPPORT_REQUEST

    @api.model
    def _may_handle(self):
        """Whether the person takes and answers support requests, as sales do on the web."""
        return self._has_permission("edit")

    @api.model
    def _mobile_list(self, name):
        """The open and answered requests the person handles, open first; or the open requests nobody has taken."""
        if name == SUPPORT_MINE:
            domain = Domain("handled_by_id", "=", self.env.uid) & Domain(
                "status", "in", (SUPPORT_OPEN, SUPPORT_ANSWERED)
            )
            # Odoo sorts a selection by the order of its values: open, then answered.
            return self.search(domain, order="status, id desc")
        return self.search(Domain("handled_by_id", "=", False) & Domain("status", "=", SUPPORT_OPEN))

    @api.model
    def _mobile_readable(self, request_id):
        """The request of the id once the person may read it; one they may not read is not found."""
        request = self.browse(request_id).exists()
        if not request:
            raise not_found(self.env)
        request.check_access("read")
        return request

    def _mobile_values(self):
        # The names of the customer, the order and the handler are read with full rights, as the web's form shows them.
        return [
            {
                "id": request.id,
                "code": request.code or "",
                "subject": request.subject or "",
                "status": request.status,
                "customer": request.customer_id.sudo().display_name or "",
                "order": request.order_id.sudo().name or "",
                "handled_by": request.handled_by_id.sudo().name or "",
                "opened_at": api_datetime(request.create_date),
            }
            for request in self
        ]

    def _mobile_detail(self):
        """The request with the messages the customer and sales wrote, and what the person may do with it."""
        self.ensure_one()
        messages = self.message_ids.filtered(self._is_discussion).sorted("id")
        answerable = self.status != SUPPORT_CLOSED and self.has_access("write")
        return {
            **self._mobile_values()[0],
            "messages": [
                {
                    "id": message.id,
                    "author": message.author_id.sudo().name or "",
                    "body": html2plaintext(message.body or ""),
                    "date": api_datetime(message.date),
                    "from_customer": self._written_by_customer(message),
                }
                for message in messages
            ],
            "actions": {"take": answerable and not self.handled_by_id, "answer": answerable},
        }

    def _take_from_phone(self):
        """Take the request as the web's Take button does. Taking it again answers it again; a request someone else
        took first is refused with already_taken."""
        self.ensure_one()
        if not self._may_handle():
            raise not_found(self.env)
        if self.sudo().handled_by_id.id == self.env.uid:
            return
        try:
            self.action_take()
        except UserError as error:
            if self.sudo().handled_by_id:
                raise LaboratoryFileError(ALREADY_TAKEN, error.args[0]) from error
            raise

    def _answer_from_phone(self, device, text, key=None):
        """Answer the customer as a reply on the web's chatter does, so the request is answered and the customer is
        notified. A request repeated with its Idempotency-Key answers nothing more."""
        self.ensure_one()
        messages = self.env[MODEL_MAIL_MESSAGE]
        sent = messages._created_with_key(device, key).sudo()
        if sent:
            if (sent.model, sent.res_id) != (self._name, self.id):
                raise LaboratoryFileError(
                    IDEMPOTENCY_CONFLICT, self.env._("This Idempotency-Key was already sent with another request.")
                )
            return
        if not self.has_access("write"):
            raise LaboratoryFileError(PERMISSION_DENIED, self.env._("You may not answer this support request."))
        if self.status == SUPPORT_CLOSED:
            raise UserError(self.env._("%s is closed.", self.display_name))
        with messages._once_per_key():
            message = self.message_post(
                body=plaintext2html(text.strip()), message_type=COMMENT, subtype_xmlid="mail.mt_comment"
            )
            if key:
                message.sudo().write({"posted_by_device_id": device.id, "idempotency_key": key})
