from odoo import SUPERUSER_ID, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tools import format_datetime

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_MOVE, MODEL_ADVANCE_PAYMENT_INV, MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import ADVANCE_FIXED, ADVANCE_FULL, ADVANCE_NONE, ADVANCE_PERCENTAGE
from odoo.addons.sol_commerce.constants.xml_ids import ALL_ORDERS_GROUP


# Đơn Hàng: the advance invoice and the notice that go out with a quotation.
class SaleOrderAdvance(models.Model):
    _inherit = MODEL_SALE_ORDER

    def _check_quotation_can_be_sent(self):
        super()._check_quotation_can_be_sent()
        if not self.advance_method:
            raise UserError(self.env._("Choose how the advance is paid, or no advance, before sending the quotation."))
        if self.advance_method == ADVANCE_NONE:
            if not (self.env.su or self.env.user.has_group(ALL_ORDERS_GROUP)):
                raise AccessError(self.env._("Only the Head of Sales can send a quotation without an advance."))
            return
        if not self.advance_mode:
            raise UserError(
                self.env._("Choose whether the advance is the full amount, a percentage or a fixed amount.")
            )
        if self.advance_mode == ADVANCE_PERCENTAGE and not 0 < self.advance_value <= 100:
            raise UserError(self.env._("The advance percentage must be above 0 and at most 100."))
        if self.advance_mode == ADVANCE_FIXED and self.advance_value <= 0:
            raise UserError(self.env._("The advance amount must be above 0."))

    def _send_quotation(self):
        quotation = super()._send_quotation()
        invoice = self._create_advance_invoice()
        self._notify_quotation_sent(quotation, invoice)
        return quotation

    def _create_advance_invoice(self):
        """Post the down payment invoice for the advance; no invoice when the quotation has no advance."""
        self.ensure_one()
        if self.advance_method == ADVANCE_NONE:
            return self.env[MODEL_ACCOUNT_MOVE]
        if self.advance_mode == ADVANCE_FIXED:
            values = {"advance_payment_method": "fixed", "fixed_amount": self.advance_value}
        else:
            percentage = 100 if self.advance_mode == ADVANCE_FULL else self.advance_value
            values = {"advance_payment_method": "percentage", "amount": percentage}
        # The wizard posts as the user when it is internal, and a salesperson cannot post on an invoice.
        order = self.with_user(SUPERUSER_ID)
        wizard = (
            self.env[MODEL_ADVANCE_PAYMENT_INV]
            .with_user(SUPERUSER_ID)
            .with_context(active_model=MODEL_SALE_ORDER, active_ids=order.ids)
            .create({**values, "sale_order_ids": [Command.set(order.ids)]})
        )
        wizard._check_amount_is_positive()
        invoice = wizard._create_invoices(order)
        invoice.action_post()
        return invoice

    def _notify_quotation_sent(self, quotation, invoice):
        """Tell the order's contact about the quotation, with its PDF attached."""
        self.ensure_one()
        deadline = format_datetime(self.env, self.payment_deadline)
        if invoice:
            body = self.env._(
                "Quotation %(code)s is ready. Pay the advance of %(amount)s before %(deadline)s.",
                code=quotation.code,
                amount=self.currency_id.format(invoice.amount_total),
                deadline=deadline,
            )
        else:
            body = self.env._(
                "Quotation %(code)s is ready. Accept it before %(deadline)s.",
                code=quotation.code,
                deadline=deadline,
            )
        self.sudo().message_post(
            body=body,
            partner_ids=self.partner_id.ids,
            attachment_ids=quotation.attachment_id.ids,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
