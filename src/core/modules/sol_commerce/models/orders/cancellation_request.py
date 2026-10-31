from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import MODEL_CANCELLATION_REQUEST, MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import (
    ACCEPTED,
    CANCELLATION_ACTION,
    CANCELLATION_TRIGGER,
    DECLINED,
    REQUESTED,
    WITHDRAWN,
)
from odoo.addons.sol_commerce.constants.xml_ids import CANCELLATION_TASK_TYPE
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_TASK,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_cancellation_request as CancellationRequestBase
else:
    CancellationRequestBase = object


# Yêu Cầu Hủy
class CancellationRequest(models.Model, CancellationRequestBase):
    _name = MODEL_CANCELLATION_REQUEST
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Cancellation Request"
    _order = "id desc"
    _rec_name = "order_id"
    _permission_actions = ("read", "create", "edit", "delete")

    if not TYPE_CHECKING:
        # The order to cancel.
        order_id = fields.Many2one(MODEL_SALE_ORDER, required=True, ondelete="restrict", index=True)
        # Why the customer wants to cancel.
        reason = fields.Text(required=True)
        # requested, accepted, declined or withdrawn.
        status = fields.Selection(
            [
                (REQUESTED, "Requested"),
                (ACCEPTED, "Accepted"),
                (DECLINED, "Declined"),
                (WITHDRAWN, "Withdrawn"),
            ],
            required=True,
            default=REQUESTED,
            index=True,
        )
        # The Odoo user who sent the request.
        requested_by_id = fields.Many2one("res.users", required=True, ondelete="restrict", index=True)
        # The salesperson who decided.
        decided_by_id = fields.Many2one("res.users", ondelete="restrict", index=True)
        # When it was decided.
        decided_at = fields.Datetime()
        # The salesperson's reply to the customer.
        reply = fields.Text()

    _order_status_idx = models.Index("(order_id, status)")

    def init(self):
        # At most one open request per order. A partial index is not a table constraint the ORM can declare.
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS medilab_cancellation_request_one_open
            ON medilab_cancellation_request (order_id)
            WHERE status = 'requested'
            """
        )

    @api.constrains("order_id", "status")
    def _check_one_open_request(self):
        for request in self.filtered(lambda item: item.status == REQUESTED):
            others = self.search(
                [
                    ("id", "!=", request.id),
                    ("order_id", "=", request.order_id.id),
                    ("status", "=", REQUESTED),
                ]
            )
            if others:
                raise UserError(self.env._("This order already has an open cancellation request."))

    @api.model_create_multi
    def create(self, vals_list):
        requests = super().create(vals_list)
        requests.filtered(lambda request: request.status == REQUESTED)._create_task()
        return requests

    def _create_task(self):
        task_type = self.env.ref(CANCELLATION_TASK_TYPE)
        for request in self:
            person = self.env[MODEL_PERSON].sudo().search([("user_id", "=", request.order_id.user_id.id)], limit=1)
            self.env[MODEL_TASK]._create_for_event(
                task_type.trigger or CANCELLATION_TRIGGER,
                request,
                assignee=person,
                note=request.reason,
            )

    def action_withdraw(self):
        self._check_open()
        for request in self:
            owner = request.requested_by_id == self.env.user or request.order_id._owned_by(self.env.user)
            if not self.env.su and not owner:
                raise UserError(self.env._("Only the customer who sent the request can withdraw it."))
        self.sudo().write({"status": WITHDRAWN})
        self.env[MODEL_TASK]._cancel_for_document(self, CANCELLATION_ACTION)
        return True

    def action_accept(self):
        self._check_open()
        for request in self:
            message = request.order_id._cancellation_block_message()
            if message:
                raise UserError(message)
            request.order_id._cancel_order()
        self._decide(ACCEPTED)
        return True

    def action_decline(self):
        self._check_open()
        for request in self:
            if not ((request.reply or "").strip()):
                raise UserError(self.env._("Write a reply to the customer."))
        self._decide(DECLINED)
        return True

    def _check_open(self):
        if any(request.status != REQUESTED for request in self):
            raise UserError(self.env._("This request has already been decided."))

    def _decide(self, status):
        self.write({"status": status, "decided_by_id": self.env.uid, "decided_at": fields.Datetime.now()})
        for request in self:
            request._notify_customer()
        self.env[MODEL_TASK]._close_for_document(self, CANCELLATION_ACTION)

    def _notify_customer(self):
        self.ensure_one()
        if self.status == ACCEPTED:
            body = self.env._("Your cancellation request was accepted. The order is cancelled.")
        else:
            body = self.env._("Your cancellation request was declined: %s", self.reply)
        partner = self.order_id.partner_id
        order = self.order_id.sudo()
        if partner:
            order.message_subscribe(partner_ids=partner.ids)
        order.message_post(body=body, partner_ids=partner.ids, subtype_xmlid="mail.mt_comment")
