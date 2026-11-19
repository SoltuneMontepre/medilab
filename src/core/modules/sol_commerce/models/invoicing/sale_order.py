from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools import SQL

from odoo.addons.sol_commerce.constants.models import (
    MODEL_ACCOUNT_MOVE,
    MODEL_ACCOUNT_PAYMENT,
    MODEL_PAYMENT_REQUEST,
    MODEL_SALE_ADVANCE_PAYMENT_INV,
    MODEL_SALE_ORDER,
)
from odoo.addons.sol_commerce.constants.tasks import AUTO_POST_CONTEXT
from odoo.addons.sol_laboratory.services.record_id import persisted_id, persisted_ids

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderBase
else:
    SaleOrderBase = object


# Đơn bán
class SaleOrder(models.Model, SaleOrderBase):
    _inherit = MODEL_SALE_ORDER

    if not TYPE_CHECKING:
        # Request that currently collects payments for the order.
        payment_request_id = fields.Many2one(MODEL_PAYMENT_REQUEST, ondelete="restrict", copy=False, readonly=True)
        # Requests issued for the order, including earlier quotation revisions.
        payment_request_ids = fields.One2many(MODEL_PAYMENT_REQUEST, "order_id", string="Payment Requests")
        # Whether an unpaid request or posted credit invoice is available for Sales to record funds against.
        can_record_collection = fields.Boolean(compute="_compute_collection_actions", compute_sudo=True)
        # Whether Sales can record written agreement because prior payments cover the revised advance.
        can_record_agreement = fields.Boolean(compute="_compute_collection_actions", compute_sudo=True)
        # Whether the accountant may draft the final invoice for completed testing on credit.
        can_invoice_credit_order = fields.Boolean(compute="_compute_collection_actions", compute_sudo=True)
        # The four fields below are computed with full rights. A salesperson reads only the invoices they sell, so computed
        # with their rights an order taken over from another salesperson shows no invoice and nothing paid or pending.
        # The invoices and credit notes of the order.
        invoice_ids = fields.Many2many(compute_sudo=True)
        # How many invoices and credit notes the order has.
        invoice_count = fields.Integer(compute_sudo=True)
        # not_paid, partial or paid, from the posted customer invoices. A draft payment does not count.
        payment_status = fields.Selection(
            [("not_paid", "Not paid"), ("partial", "Partially paid"), ("paid", "Paid")],
            compute="_compute_payment_status",
            compute_sudo=True,
        )
        # Draft cash and bank transfers on this order's invoices. A confirmed or rejected payment is not included.
        pending_amount = fields.Monetary(
            string="Pending amount", compute="_compute_pending_amount", currency_field="currency_id", compute_sudo=True
        )

    @api.depends(
        "invoice_ids.payment_state",
        "invoice_ids.state",
        "invoice_ids.move_type",
        "invoice_ids.amount_residual",
        "invoice_ids.line_ids.matched_credit_ids",
        "invoice_ids.line_ids.matched_debit_ids",
        "payment_request_ids.verified_amount",
        "amount_total",
    )
    def _compute_payment_status(self):
        for order in self:
            verified = order._verified_order_amount()
            if order.currency_id.is_zero(verified):
                order.payment_status = "not_paid"
            elif order.currency_id.compare_amounts(verified, order.amount_total) >= 0:
                order.payment_status = "paid"
            else:
                order.payment_status = "partial"

    def _verified_order_amount(self):
        self.ensure_one()
        invoices = self.sudo().invoice_ids.filtered(
            lambda move: (
                move.state == "posted" and move.move_type == "out_invoice" and move.invoice_kind != "adjustment"
            )
        )
        total = 0.0
        for invoice in invoices:
            partials, _exchange_moves = invoice._get_reconciled_invoices_partials()
            total += sum(
                amount
                for _partial, amount, counterpart in partials
                if counterpart.move_id.origin_payment_id or counterpart.move_id.statement_line_id
            )
        return total

    @api.depends(
        "invoice_ids", "invoice_ids.payment_state", "invoice_ids.amount_residual", "payment_request_ids.pending_amount"
    )
    def _compute_pending_amount(self):
        for order in self:
            order.pending_amount = sum(order._pending_collections(include_online=False).mapped("amount"))

    def _pending_collections(self, *, include_online=True):
        self.ensure_one()
        methods = ("cash", "bank_transfer", "online") if include_online else ("cash", "bank_transfer")
        return (
            self.env[MODEL_ACCOUNT_PAYMENT]
            .sudo()
            .search(
                [
                    "|",
                    ("payment_request_id.order_id", "in", self.ids),
                    ("invoice_ids", "in", self.sudo().invoice_ids.ids),
                    ("state", "=", "draft"),
                    ("method", "in", methods),
                ]
            )
        )

    def _lock_payment_orders(self):
        orders = self.sudo()
        if orders:
            orders.flush_recordset()
            self.env.cr.execute(
                SQL("SELECT id FROM sale_order WHERE id IN %s ORDER BY id FOR UPDATE", tuple(orders.ids))
            )
            # Make request/payment inserts on different tables visible to a concurrent order transaction on retry.
            self.env.cr.execute(SQL("UPDATE sale_order SET write_date = write_date WHERE id IN %s", tuple(orders.ids)))
            orders.invalidate_recordset(
                ["payment_request_id", "state", "order_status", "quotation_ids", "payment_deadline"]
            )

    def _check_no_pending_collection(self):
        if any(order._pending_collections() for order in self):
            raise UserError(self.env._("Confirm or reject the pending payment before changing the quotation or order."))

    def _payment_request_payos_available(self):
        return self.env[MODEL_ACCOUNT_MOVE]._portal_payos_available()

    @api.depends(
        "payment_request_id.state",
        "payment_request_id.amount",
        "payment_request_id.carried_amount",
        "quotation_ids.status",
        "state",
        "on_credit",
        "test_request_id.status",
        "invoice_ids.amount_residual",
    )
    def _compute_collection_actions(self):
        for order in self:
            request = order.payment_request_id
            quotation = order._latest_quotation()
            order.can_record_collection = bool(order._collection_target() and order.state != "cancel")
            order.can_record_agreement = bool(
                quotation.status == "sent"
                and quotation.replaces_id
                and order.state == "sent"
                and request.carried_amount
                and not request.amount
            )
            order.can_invoice_credit_order = order._credit_invoice_eligible()

    def _credit_invoice_eligible(self):
        self.ensure_one()
        return self.on_credit and self.sudo().test_request_id.status in ("completed", "reported")

    def _collection_target(self):
        self.ensure_one()
        order = self.sudo()
        if order.payment_request_id.state in ("open", "expired"):
            return order.payment_request_id
        if order.on_credit:
            return order.invoice_ids.filtered(
                lambda invoice: (
                    invoice.state == "posted" and invoice.invoice_kind == "final" and bool(invoice.amount_residual)
                )
            )[:1]
        return self.env[MODEL_PAYMENT_REQUEST]

    def action_record_collection(self, amount, method, received_at=None, reference=None):
        """Record Sales' receipt of cash or a bank transfer for this order."""
        self.ensure_one()
        if self.env.user.share:
            raise UserError(self.env._("Only Sales can record a collection on behalf of the customer."))
        self.check_access("write")
        self._lock_payment_orders()
        target = self._collection_target()
        if not target or self.state == "cancel":
            raise UserError(self.env._("This order has no payment request or unpaid final invoice."))
        payments = self.env[MODEL_ACCOUNT_PAYMENT].sudo()
        if target._name == MODEL_PAYMENT_REQUEST:
            payment = payments._create_request_payment(
                target,
                amount,
                method,
                received_at=received_at,
                reference=reference,
                record_received=True,
            )
        else:
            payment = payments.create_pending_payment(target, amount, method)
            payment.write({"received_at": payments._receipt_time(received_at), "memo": reference or payment.memo})
        return persisted_id(payment)

    def create_final_invoice(self):
        """Draft the invoice for what is left after the advance. The accountant posts it."""
        self.ensure_one()
        self._check_manual_invoice_allowed()
        return self._draft_final_invoice()

    def _check_manual_invoice_allowed(self):
        for order in self.filtered(lambda item: bool(item._latest_quotation())):
            if not order._credit_invoice_eligible():
                raise UserError(self.env._("The final invoice is created after testing for orders on credit."))

    def _draft_final_invoice(self):
        self.ensure_one()
        invoices = self._create_invoices(final=True)
        if not invoices:
            raise UserError(self.env._("This order has nothing left to invoice."))
        invoices.write({"invoice_kind": "final", "order_id": self.id})
        return invoices

    def _draft_installment_invoice(self, amount):
        self.ensure_one()
        wizard = self.env[MODEL_SALE_ADVANCE_PAYMENT_INV].create(
            {
                "advance_payment_method": "fixed",
                "fixed_amount": amount,
                "sale_order_ids": [Command.set(persisted_ids(self))],
            }
        )
        return wizard._create_invoices(self)

    def _create_collection_invoice(self, request, amount):
        """Invoice a verified payment, deducting all installments when the balance is settled."""
        self.ensure_one()
        closing = request.kind == "balance" and self.currency_id.compare_amounts(amount, request.remaining_amount) >= 0
        invoices = self._draft_final_invoice() if closing else self._draft_installment_invoice(amount)
        invoices.with_context(**{AUTO_POST_CONTEXT: True}).write(
            {
                "invoice_kind": "advance" if request.kind == "advance" else "final",
                "order_id": self.id,
                "payment_request_id": request.id,
                "invoice_payment_term_id": False,
                "invoice_date_due": fields.Date.context_today(self),
            }
        )
        invoices.action_post()
        return invoices
