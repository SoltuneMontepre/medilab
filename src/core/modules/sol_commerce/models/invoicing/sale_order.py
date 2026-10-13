from odoo import models
from odoo.exceptions import UserError
from odoo.fields import Command

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ADVANCE_PAYMENT_INV, MODEL_SALE_ORDER


# Đơn bán
class SaleOrder(models.Model):
    _inherit = MODEL_SALE_ORDER

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
