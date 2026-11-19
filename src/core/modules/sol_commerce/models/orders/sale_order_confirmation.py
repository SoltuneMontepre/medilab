from contextvars import ContextVar
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.sol_commerce.constants.models import (
    MODEL_CUSTOMER_SALES_TERMS,
    MODEL_PAYMENT_REQUEST,
    MODEL_SALE_ORDER,
)
from odoo.addons.sol_commerce.constants.notifications import EVENT_BALANCE_REQUESTED
from odoo.addons.sol_commerce.constants.orders import (
    ADVANCE_NONE,
    QUOTATION_ACCEPTED,
    QUOTATION_REPLACED,
    STATUS_CLAIMED,
    STATUS_CONFIRMED,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_CUSTOMER,
    MODEL_MAIL_MESSAGE,
    MODEL_TASK,
    MODEL_TASK_TYPE,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_COLLECTION_CODE

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderConfirmationBase
else:
    SaleOrderConfirmationBase = object

# Ids of the orders that passed the checks and whose Odoo confirmation is running now. Only the code below fills it,
# so a caller cannot ask for the confirmation to skip the checks the way a context key would allow.
CONFIRMING_ORDER_IDS = ContextVar("medilab_confirming_order_ids", default=frozenset())


# Đơn Hàng: confirming the order creates its test request, whose sample collection sales then start.
class SaleOrderConfirmation(models.Model, SaleOrderConfirmationBase):
    _inherit = MODEL_SALE_ORDER

    if not TYPE_CHECKING:
        # The test request the confirmed order produced.
        test_request_id = fields.Many2one(
            MODEL_TEST_REQUEST, string="Test Request", ondelete="restrict", copy=False, index="btree_not_null"
        )
        # True when this order was confirmed on the customer's approved credit terms.
        on_credit = fields.Boolean(readonly=True, copy=False)
        # True while the order still needs payment before collecting its samples.
        show_unpaid_warning = fields.Boolean(compute="_compute_show_unpaid_warning", compute_sudo=True)

    @api.depends("payment_status", "on_credit")
    def _compute_show_unpaid_warning(self):
        for order in self:
            order.show_unpaid_warning = not order._can_collect_samples()

    def _can_collect_samples(self):
        self.ensure_one()
        return self.on_credit or self.payment_status == "paid" or self.currency_id.is_zero(self.amount_total)

    def action_confirm(self):
        # Odoo's own Confirm button and every other caller go through the same checks.
        if self and set(self.ids) <= CONFIRMING_ORDER_IDS.get():
            return super().action_confirm()
        return self.action_confirm_order()

    def action_confirm_order(self):
        """Confirm the order the customer accepted and create its test request."""
        self.check_access("write")
        self._lock_payment_orders()
        for order in self:
            order._check_can_be_confirmed()
        for order in self:
            order._confirm_order()
        odoo_pending = self.filtered(lambda order: order.state in ("draft", "sent"))
        if odoo_pending:
            token = CONFIRMING_ORDER_IDS.set(CONFIRMING_ORDER_IDS.get() | frozenset(odoo_pending.ids))
            try:
                odoo_pending.action_confirm()
            finally:
                CONFIRMING_ORDER_IDS.reset(token)
        return True

    def _check_can_be_confirmed(self):
        self.ensure_one()
        latest = self._latest_quotation()
        # A new order is also draft. Revision is the draft that follows a quotation already sent.
        if self.state == "draft" and latest:
            raise UserError(self.env._("The quotation is being revised. Send the new revision first."))
        if self.order_status != STATUS_CLAIMED:
            raise UserError(self.env._("Only a claimed order can be confirmed."))
        if latest.status == QUOTATION_REPLACED:
            raise UserError(self.env._("A replaced quotation cannot be confirmed."))
        if latest.status != QUOTATION_ACCEPTED:
            raise UserError(self.env._("The customer must accept the quotation before the order is confirmed."))
        payment_request = self.sudo().payment_request_id
        if (
            payment_request.kind == "advance" and payment_request.state != "funded"
        ) or latest.sudo().advance_invoice_id.amount_residual:
            raise UserError(self.env._("Verify the full requested advance before confirming the order."))

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
                committed_date=self.committed_date,
                requested_date=self.requested_date,
                priority=self.priority,
                turnaround_days=self.turnaround_days,
                report_recipient=self.partner_id if self.partner_id != self.customer_id else False,
            )
        )
        on_credit = self._qualifies_for_credit(customer)
        self.sudo().on_credit = on_credit
        self._set_status(STATUS_CONFIRMED, {"test_request_id": request.id, "confirmed_at": fields.Datetime.now()})
        if not on_credit:
            self._request_balance()
        request.action_confirm()

    def _qualifies_for_credit(self, customer):
        self.ensure_one()
        return self.advance_method == ADVANCE_NONE and bool(
            self.env[MODEL_CUSTOMER_SALES_TERMS]
            .sudo()
            .search_count([("customer_id", "=", customer.id), ("allow_credit", "=", True)], limit=1)
        )

    def _request_balance(self):
        self.ensure_one()
        amount = self.currency_id.round(self.amount_total - self._verified_order_amount())
        if amount <= 0:
            return
        request = (
            self.env[MODEL_PAYMENT_REQUEST]
            .sudo()
            .create(
                {
                    "kind": "balance",
                    "order_id": self.id,
                    "quotation_id": self._latest_quotation().id,
                    "amount": amount,
                    "carried_amount": self._verified_order_amount(),
                }
            )
        )
        self.sudo().payment_request_id = request
        order = self.with_context(lang=self._get_lang())
        order.env[MODEL_MAIL_MESSAGE].sudo().raise_event(
            EVENT_BALANCE_REQUESTED,
            order.sudo(),
            f"payment-request:{request.id}:sent",
            order.env._(
                "Pay the remaining %(amount)s for order %(order)s before sample collection.",
                amount=order.currency_id.format(amount),
                order=order.name,
            ),
            partners=order.partner_id,
        )

    def _release_test_request(self):
        for request in self.sudo().test_request_id.filtered(lambda item: item.status == "confirmed"):
            request._set_status("paid")

    def _keep_order_numbers(self):
        """Write each order's number on its test request, which keeps it once uninstalling E-commerce drops the link."""
        for order in self.sudo().search([("test_request_id", "!=", False)]):
            order.test_request_id.order_number = order.name

    def action_start_sample_collection(self):
        """Queue one unassigned sample collection task of the confirmed order's test request for sample delivery
        staff, at the customer's address; they claim it and plan its time."""
        self.check_access("write")
        for order in self:
            if order.order_status != STATUS_CONFIRMED:
                raise UserError(self.env._("The order must be confirmed before the samples are collected."))
            if not order._can_collect_samples():
                raise UserError(self.env._("Verify the order balance before collecting its samples."))
        task_type = self.env[MODEL_TASK_TYPE].sudo().search([("code", "=", SAMPLE_COLLECTION_CODE)], limit=1)
        if task_type.route != "role":
            raise UserError(
                self.env._("Route the %s task type to the role of sample delivery staff first.", task_type.name)
            )
        tasks = self.env[MODEL_TASK].sudo()
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
