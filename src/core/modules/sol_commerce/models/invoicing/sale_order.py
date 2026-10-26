from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ADVANCE_PAYMENT_INV, MODEL_SALE_ORDER

PAID_STATES = ("paid", "in_payment", "reversed")


# Đơn bán
class SaleOrder(models.Model):
    _inherit = MODEL_SALE_ORDER

    # What an order shows of its invoices is computed with full rights: a salesperson reads the order without holding
    # rights on invoices, and a compute run with theirs fails or sees no invoice.
    invoice_ids = fields.Many2many(compute_sudo=True)
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

    @api.depends("invoice_ids.payment_state", "invoice_ids.state", "invoice_ids.move_type")
    def _compute_payment_status(self):
        for order in self:
            invoices = order.invoice_ids.filtered(
                lambda move: move.state == "posted" and move.move_type == "out_invoice"
            )
            if not invoices or all(move.payment_state == "not_paid" for move in invoices):
                order.payment_status = "not_paid"
            elif all(move.payment_state in PAID_STATES for move in invoices):
                order.payment_status = "paid"
            else:
                order.payment_status = "partial"

    @api.depends("invoice_ids", "invoice_ids.payment_state", "invoice_ids.amount_residual")
    def _compute_pending_amount(self):
        payments = self.env["account.payment"]
        for order in self:
            invoices = order.invoice_ids
            pending = payments.browse()
            if invoices:
                pending = payments.search(
                    [
                        ("invoice_ids", "in", invoices.ids),
                        ("state", "=", "draft"),
                        ("method", "in", ("cash", "bank_transfer")),
                    ]
                )
            order.pending_amount = sum(payment.amount for payment in pending)

    def create_advance_invoice(self, amount=None, percentage=None):
        """Post one down-payment invoice for this order. Sending a quotation calls this through _on_quotation_sent."""
        self.ensure_one()
        if percentage is not None and amount is not None:
            raise UserError(self.env._("An advance is a fixed amount or a percentage, not both."))
        if percentage is not None:
            method = "percentage"
            values = {"amount": percentage}
        else:
            method = "fixed"
            values = {"fixed_amount": self.amount_total if amount is None else amount}
        wizard = self.env[MODEL_SALE_ADVANCE_PAYMENT_INV].create(
            {
                "advance_payment_method": method,
                "sale_order_ids": [Command.set(self.ids)],
                **values,
            }
        )
        invoices = wizard._create_invoices(self)
        invoices.write({"invoice_kind": "advance", "order_id": self.id})
        invoices.action_post()
        return invoices

    def create_final_invoice(self):
        """Draft the invoice for what is left after the advance. The accountant posts it."""
        self.ensure_one()
        invoices = self._create_invoices(final=True)
        if not invoices:
            raise UserError(self.env._("This order has nothing left to invoice."))
        invoices.write({"invoice_kind": "final", "order_id": self.id})
        return invoices

    def _on_quotation_sent(self, amount=None, percentage=None):
        # Quotations call this when sales sends one that asks for an advance. This module does not send the quotation.
        return self.create_advance_invoice(amount=amount, percentage=percentage)
