from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import (
    APPROVAL_APPROVED,
    APPROVAL_NONE,
    STATUS_COMPLETED,
    STATUS_CONFIRMED,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_APPROVAL_MIXIN, MODEL_PERSON, MODEL_TASK, MODEL_TASK_TYPE
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_COLLECTION_CODE

# What the customer and sales agreed: edits stop once a signature stands.
APPROVAL_CONTENT_FIELDS = frozenset({"customer_id", "partner_id", "payment_deadline", "validity_date"})


# Đơn Hàng: the order is approved by signatures.
class SaleOrderApproval(models.Model):
    _name = MODEL_SALE_ORDER
    _inherit = [MODEL_SALE_ORDER, MODEL_APPROVAL_MIXIN]
    _audit_children = ("order_line", "quotation_ids", "sample_ids", "cancellation_request_ids", "support_request_ids")

    def action_request_approval(self):
        """Sign the first level, which asks the next levels to approve the confirmed order."""
        self.ensure_one()
        if self.approval_status != APPROVAL_NONE:
            raise UserError(self.env._("The approval of this order was already requested."))
        return self.action_sign()

    def action_sign(self):
        self.ensure_one()
        if self.order_status != STATUS_CONFIRMED:
            raise UserError(self.env._("Only a confirmed order can be signed."))
        return super().action_sign()

    def action_start_sample_collection(self):
        """Queue one unassigned sample collection task of the approved order's test request for sample delivery staff,
        at the customer's address; they claim it and plan its time."""
        self.check_access("write")
        task_type = self.env[MODEL_TASK_TYPE].sudo().search([("code", "=", SAMPLE_COLLECTION_CODE)], limit=1)
        tasks = self.env[MODEL_TASK].sudo()
        for order in self:
            if order.approval_status != APPROVAL_APPROVED:
                raise UserError(self.env._("The order must be approved before the samples are collected."))
        if task_type.route != "role":
            raise UserError(
                self.env._("Route the %s task type to the role of sample delivery staff first.", task_type.name)
            )
        for order in self:
            request = order.sudo().test_request_id
            document = Domain("document_model", "=", request._name) & Domain("document_id", "=", request.id)
            if tasks.search_count(document & Domain("type_id", "=", task_type.id) & tasks._in_use_domain(), limit=1):
                raise UserError(self.env._("Order %s already has an open sample collection task.", order.name))
            tasks.create(
                {
                    "type_id": task_type.id,
                    "name": f"{task_type.name}: {order.name}, {order.customer_id.name}",
                    "document_model": request._name,
                    "document_id": request.id,
                    "note": order.customer_id._display_address(),
                }
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._("The sample collection task waits in the queue of sample delivery staff."),
            },
        }

    def _approval_requester(self):
        self.ensure_one()
        return self.env[MODEL_PERSON].sudo().search([("user_id", "=", self.user_id.id)], limit=1)

    def _approval_content_fields(self):
        return APPROVAL_CONTENT_FIELDS

    def _approval_process_completed(self):
        return self.order_status == STATUS_COMPLETED

    def _approval_set_state(self, state):
        self.write(
            {"approval_status": state, "approved_at": fields.Datetime.now() if state == APPROVAL_APPROVED else False}
        )

    def _approval_notify_rejected(self, reason):
        self.ensure_one()
        self.sudo().message_post(
            body=self.env._("The approval of this order was rejected: %s", reason),
            partner_ids=self.user_id.partner_id.ids,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
