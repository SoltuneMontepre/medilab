from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import (
    ADVANCE_PAID_STATES,
    QUOTATION_ACCEPTED,
    QUOTATION_REPLACED,
    STATUS_CLAIMED,
    STATUS_CONFIRMED,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER, MODEL_TEST_REQUEST

# Context key that lets Odoo's own confirmation run once the order passed the checks above.
ODOO_CONFIRM_CONTEXT = "medilab_odoo_confirm"


# Đơn Hàng: confirming the order creates its test request.
class SaleOrderConfirmation(models.Model):
    _inherit = MODEL_SALE_ORDER

    # The test request the confirmed order produced.
    test_request_id = fields.Many2one(
        MODEL_TEST_REQUEST, string="Test Request", ondelete="restrict", copy=False, index="btree_not_null"
    )
    # True when no invoice of the order is paid; confirming the order is still allowed.
    show_unpaid_warning = fields.Boolean(compute="_compute_show_unpaid_warning")

    @api.depends("invoice_ids.payment_state")
    def _compute_show_unpaid_warning(self):
        for order in self:
            order.show_unpaid_warning = not order._is_paid()

    def _is_paid(self):
        self.ensure_one()
        return any(
            invoice.move_type == "out_invoice" and invoice.payment_state in ADVANCE_PAID_STATES
            for invoice in self.sudo().invoice_ids
        )

    def action_confirm(self):
        # Odoo's own Confirm button and every other caller go through the same checks.
        if self.env.context.get(ODOO_CONFIRM_CONTEXT):
            return super().action_confirm()
        return self.action_confirm_order()

    def action_confirm_order(self):
        """Confirm the order the customer accepted and create its test request."""
        for order in self:
            order._check_can_be_confirmed()
        for order in self:
            order._confirm_order()
        odoo_pending = self.filtered(lambda order: order.state in ("draft", "sent"))
        if odoo_pending:
            odoo_pending.with_context(**{ODOO_CONFIRM_CONTEXT: True}).action_confirm()
        return True

    def _check_can_be_confirmed(self):
        self.ensure_one()
        if self.order_status != STATUS_CLAIMED:
            raise UserError(self.env._("Only a claimed order can be confirmed."))
        latest = self._latest_quotation()
        if latest.status == QUOTATION_REPLACED:
            raise UserError(self.env._("A replaced quotation cannot be confirmed."))
        if latest.status != QUOTATION_ACCEPTED:
            raise UserError(self.env._("The customer must accept the quotation before the order is confirmed."))

    def _confirm_order(self):
        self.ensure_one()
        customer = self.env[MODEL_CUSTOMER].sudo().search([("partner_id", "=", self.customer_id.id)], limit=1)
        if not customer:
            raise UserError(self.env._("%s is not a customer yet. Create the customer first.", self.customer_id.name))
        request = (
            self.env[MODEL_TEST_REQUEST]
            .sudo()
            .create_from_order(
                customer,
                [sample._test_request_values() for sample in self.sample_ids],
                expected_date=self.expected_result_date,
                report_recipient=self.partner_id if self.partner_id != self.customer_id else False,
            )
        )
        self._set_status(STATUS_CONFIRMED, {"test_request_id": request.id})
