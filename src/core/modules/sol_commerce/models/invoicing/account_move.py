from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_MOVE, MODEL_SALE_ORDER

BILLING_GROUP = "account.group_account_invoice"
ADMINISTRATOR_GROUP = "base.group_system"


# Hóa đơn
class AccountMove(models.Model):
    _inherit = MODEL_ACCOUNT_MOVE

    # advance, final or adjustment; empty on journal entries that are not laboratory invoices.
    invoice_kind = fields.Selection(
        [("advance", "Advance"), ("final", "Final"), ("adjustment", "Adjustment")],
        string="Invoice Kind",
    )
    # The order this invoice bills. Empty until orders are installed; the sale lines still link the invoice.
    order_id = fields.Many2one(MODEL_SALE_ORDER, string="Order", index=True, ondelete="restrict")
    # The posted invoice a raising adjustment adds to.
    adjusted_invoice_id = fields.Many2one(MODEL_ACCOUNT_MOVE, string="Adjusted Invoice", ondelete="restrict", index=True)
    # Raising adjustments of this invoice.
    raising_adjustment_ids = fields.One2many(MODEL_ACCOUNT_MOVE, "adjusted_invoice_id", string="Raising Adjustments")
    # What is still owed: the residual, minus posted lowering adjustments, plus posted raising ones.
    amount_owed = fields.Monetary(compute="_compute_amount_owed", currency_field="currency_id")

    @api.depends(
        "amount_residual",
        "invoice_kind",
        "move_type",
        "reversal_move_ids.amount_residual",
        "reversal_move_ids.state",
        "reversal_move_ids.invoice_kind",
        "raising_adjustment_ids.amount_residual",
        "raising_adjustment_ids.state",
    )
    def _compute_amount_owed(self):
        for move in self:
            if move.move_type != "out_invoice" or move.invoice_kind not in ("advance", "final"):
                move.amount_owed = move.amount_residual
                continue
            lowering = move.reversal_move_ids.filtered(
                lambda refund: refund.state == "posted"
                and refund.invoice_kind == "adjustment"
                and refund.amount_residual
            )
            raises = move.raising_adjustment_ids.filtered(lambda invoice: invoice.state == "posted")
            # A reconciled credit note is already in amount_residual. Only an open one is subtracted here.
            move.amount_owed = (
                move.amount_residual - sum(lowering.mapped("amount_residual")) + sum(raises.mapped("amount_residual"))
            )

    def button_draft(self):
        locked = self.filtered(lambda move: move.invoice_kind and move.state == "posted")
        if locked:
            raise UserError(self.env._("A posted invoice cannot be edited. Correct it with an adjustment invoice."))
        return super().button_draft()

    def action_post(self):
        if self.filtered("invoice_kind"):
            self._check_billing()
        return super().action_post()

    def action_adjust(self, difference):
        """Post an adjustment of the signed difference. A negative difference is a credit note."""
        self.ensure_one()
        self._check_billing()
        if self.state != "posted" or self.move_type != "out_invoice" or self.invoice_kind not in ("advance", "final"):
            raise UserError(self.env._("Only a posted advance or final invoice can be adjusted."))
        if not difference:
            raise UserError(self.env._("An adjustment needs a difference."))
        self.env.cr.execute("SELECT id FROM account_move WHERE id = %s FOR UPDATE", (self.id,))
        if difference < 0:
            move = self._create_lowering_adjustment(abs(difference))
        else:
            move = self._create_raising_adjustment(difference)
        move.action_post()
        if difference < 0:
            self._reconcile_adjustment(move)
        return move

    def _portal_payos_available(self):
        """Whether this customer may start PayOS. Credentials stay on the server."""
        self.ensure_one()
        provider = self.env.ref("sol_commerce.payment_provider_payos", raise_if_not_found=False)
        method = self.env.ref("sol_commerce.payment_method_payos_qr", raise_if_not_found=False)
        if not provider or not method:
            return False
        provider = provider.sudo()
        method = method.sudo()
        return bool(provider.is_published and method.active)

    def action_print_invoice(self):
        self._check_billing()
        return self.env.ref("account.account_invoices").report_action(self)

    def _check_billing(self):
        if self.env.su or self.env.user.has_group(BILLING_GROUP) or self.env.user.has_group(ADMINISTRATOR_GROUP):
            return
        raise AccessError(self.env._("Only the accountant can post, adjust or print an invoice."))

    def _create_lowering_adjustment(self, amount):
        return self.env[MODEL_ACCOUNT_MOVE].create(
            {
                "move_type": "out_refund",
                "invoice_kind": "adjustment",
                "partner_id": self.partner_id.id,
                "order_id": self.order_id.id,
                "reversed_entry_id": self.id,
                "invoice_date": fields.Date.context_today(self),
                "invoice_line_ids": [Command.create(self._adjustment_line_values(amount))],
            }
        )

    def _create_raising_adjustment(self, amount):
        return self.env[MODEL_ACCOUNT_MOVE].create(
            {
                "move_type": "out_invoice",
                "invoice_kind": "adjustment",
                "partner_id": self.partner_id.id,
                "order_id": self.order_id.id,
                "adjusted_invoice_id": self.id,
                "invoice_date": fields.Date.context_today(self),
                "invoice_line_ids": [Command.create(self._adjustment_line_values(amount))],
            }
        )

    def _reconcile_adjustment(self, refund):
        refund_lines = refund.line_ids.filtered(
            lambda line: line.account_type == "asset_receivable" and not line.reconciled
        )
        invoice_lines = self.line_ids.filtered(
            lambda line: line.account_type == "asset_receivable" and not line.reconciled
        )
        if refund_lines and invoice_lines:
            (refund_lines + invoice_lines).reconcile()

    def _adjustment_line_values(self, amount):
        # The difference follows the taxes of the invoice lines it corrects.
        taxes = self.invoice_line_ids.filtered(lambda line: line.display_type == "product").tax_ids
        return {
            "name": self.env._("Adjustment of %s", self.name or self.env._("invoice")),
            "quantity": 1,
            "price_unit": amount,
            "tax_ids": [Command.set(taxes.ids)],
        }
