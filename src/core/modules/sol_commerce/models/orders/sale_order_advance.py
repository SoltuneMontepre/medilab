from typing import TYPE_CHECKING

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools import format_datetime

from odoo.addons.sol_commerce.constants.models import MODEL_PAYMENT_REQUEST, MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.notifications import EVENT_QUOTATION_SENT
from odoo.addons.sol_commerce.constants.orders import (
    ADVANCE_FIXED,
    ADVANCE_FULL,
    ADVANCE_NONE,
    ADVANCE_PERCENTAGE,
)
from odoo.addons.sol_commerce.constants.xml_ids import ALL_ORDERS_GROUP
from odoo.addons.sol_laboratory.constants.models import MODEL_MAIL_MESSAGE

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderAdvanceBase
else:
    SaleOrderAdvanceBase = object


# Đơn Hàng: the advance payment request and notice sent with a quotation.
class SaleOrderAdvance(models.Model, SaleOrderAdvanceBase):
    _inherit = MODEL_SALE_ORDER

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        fields = super().fields_get(allfields, attributes)
        if self.env.su or self.env.user.has_group(ALL_ORDERS_GROUP):
            return fields
        # Only the Head of Sales is offered no advance.
        for name in ("advance_mode", "advance_method"):
            field = fields.get(name)
            if field and "selection" in field:
                field["selection"] = [choice for choice in field["selection"] if choice[0] != ADVANCE_NONE]
        return fields

    def _quotation_missing_field_errors(self, lines):
        missing = super()._quotation_missing_field_errors(lines)
        if not self.advance_mode:
            missing.append(
                self.env._("Choose whether the advance is the full amount, a percentage, a fixed amount or none.")
            )
        elif self.advance_mode != ADVANCE_NONE and not self.payment_method:
            missing.append(self.env._("Choose how the customer pays before sending the quotation."))
        return missing

    def _check_quotation_can_be_sent(self):
        super()._check_quotation_can_be_sent()
        if self.sudo()._latest_quotation().advance_invoice_id.amount_residual:
            raise UserError(self.env._("Settle the existing advance invoice before sending a revision."))
        if not self.advance_mode:
            raise UserError(
                self.env._("Choose whether the advance is the full amount, a percentage, a fixed amount or none.")
            )
        if self.advance_mode == ADVANCE_NONE:
            if not (self.env.su or self.env.user.has_group(ALL_ORDERS_GROUP)):
                raise UserError(self.env._("Only the Head of Sales can send a quotation without an advance."))
            return
        # Without an advance nothing is asked when sending, so the payment method may wait for the balance.
        if not self.payment_method:
            raise UserError(self.env._("Choose how the customer pays before sending the quotation."))
        if self.advance_mode == ADVANCE_PERCENTAGE and not 0 < self.advance_value <= 100:
            raise UserError(self.env._("The advance percentage must be above 0 and at most 100."))
        if self.advance_mode == ADVANCE_FIXED and self.advance_value <= 0:
            raise UserError(self.env._("The advance amount must be above 0."))

    def _send_quotation(self):
        previous = self.sudo().payment_request_id
        quotation = super()._send_quotation()
        previous._supersede()
        request = self._make_advance_request(quotation)
        self.sudo().payment_request_id = request
        self._notify_quotation_sent(quotation, request)
        return quotation

    def _make_advance_request(self, quotation):
        self.ensure_one()
        requests = self.env[MODEL_PAYMENT_REQUEST].sudo()
        if self.advance_method == ADVANCE_NONE:
            return requests.browse()
        if self.advance_mode == ADVANCE_FIXED:
            advance = self.advance_value
        elif self.advance_mode == ADVANCE_FULL:
            advance = quotation.amount_total
        else:
            advance = quotation.amount_total * self.advance_value / 100
        carried = self._verified_order_amount()
        amount = max(self.currency_id.round(advance - carried), 0)
        return requests.create(
            {
                "order_id": self.id,
                "quotation_id": quotation.id,
                "kind": "advance",
                "advance_method": self.advance_method,
                "amount": amount,
                "carried_amount": carried,
                "deadline": self.payment_deadline,
                "state": "open" if amount else "funded",
            }
        )

    def _notify_quotation_sent(self, quotation, request):
        """Tell the order's contact about the quotation in the contact's language, with its PDF attached."""
        self.ensure_one()
        order = self.with_context(lang=self._get_lang())
        deadline = format_datetime(order.env, order.payment_deadline)
        if request and request.amount:
            body = order.env._(
                "Quotation %(code)s is ready. Pay the advance of %(amount)s before %(deadline)s.",
                code=quotation.code,
                amount=order.currency_id.format(request.amount),
                deadline=deadline,
            )
        else:
            body = order.env._(
                "Quotation %(code)s is ready. Accept it before %(deadline)s.",
                code=quotation.code,
                deadline=deadline,
            )
        custom_body = self.env.context.get("medilab_quotation_email_body")
        if custom_body:
            body = custom_body
        order.env[MODEL_MAIL_MESSAGE].raise_event(
            EVENT_QUOTATION_SENT,
            order.sudo(),
            f"quotation:{quotation.id}:sent",
            body,
            partners=order.partner_id,
            attachments=quotation.attachment_id,
        )
