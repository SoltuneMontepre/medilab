from datetime import datetime
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command, Domain

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_MOVE, MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.notifications import EVENT_INVOICE_SENT
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN
from odoo.addons.sol_laboratory.constants.notifications import VIETNAM_ZONE

BILLING_GROUP = "account.group_account_invoice"
ADMINISTRATOR_GROUP = "base.group_system"
VIETNAM = ZoneInfo(VIETNAM_ZONE)


# Hóa đơn
class AccountMove(models.Model):
    # _name is required to add a mixin to an Odoo model. The audit mixin comes first so it wraps Odoo's write.
    _name = MODEL_ACCOUNT_MOVE
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_ACCOUNT_MOVE]

    # advance, final or adjustment; empty on journal entries that are not laboratory invoices.
    invoice_kind = fields.Selection(
        [("advance", "Advance"), ("final", "Final"), ("adjustment", "Adjustment")],
        string="Invoice Kind",
    )
    # The order this invoice bills. Empty until orders are installed; the sale lines still link the invoice.
    order_id = fields.Many2one(MODEL_SALE_ORDER, string="Order", index=True, ondelete="restrict")
    # The posted invoice a raising adjustment adds to.
    adjusted_invoice_id = fields.Many2one(
        MODEL_ACCOUNT_MOVE, string="Adjusted Invoice", ondelete="restrict", index=True
    )
    # Raising adjustments of this invoice.
    raising_adjustment_ids = fields.One2many(MODEL_ACCOUNT_MOVE, "adjusted_invoice_id", string="Raising Adjustments")
    # What is still owed: the residual, minus posted lowering adjustments, plus posted raising ones.
    amount_owed = fields.Monetary(compute="_compute_amount_owed", currency_field="currency_id")
    # Posted advance or final invoice whose due date in Vietnam has passed and that is not fully paid.
    is_overdue = fields.Boolean(compute="_compute_is_overdue", search="_search_is_overdue")

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
                lambda refund: (
                    refund.state == "posted" and refund.invoice_kind == "adjustment" and refund.amount_residual
                )
            )
            raises = move.raising_adjustment_ids.filtered(lambda invoice: invoice.state == "posted")
            # A reconciled credit note is already in amount_residual. Only an open one is subtracted here.
            move.amount_owed = (
                move.amount_residual - sum(lowering.mapped("amount_residual")) + sum(raises.mapped("amount_residual"))
            )

    def _compute_is_overdue(self):
        today = datetime.now(VIETNAM).date()
        for move in self:
            move.is_overdue = bool(
                move.move_type == "out_invoice"
                and move.state == "posted"
                and move.invoice_kind in ("advance", "final")
                and move.payment_state in ("not_paid", "partial")
                and move.invoice_date_due
                and move.invoice_date_due < today
            )

    def _search_is_overdue(self, operator, value):
        today = datetime.now(VIETNAM).date()
        overdue = Domain(
            [
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("invoice_kind", "in", ("advance", "final")),
                ("payment_state", "in", ("not_paid", "partial")),
                ("invoice_date_due", "<", today),
            ]
        )
        wanted = bool(value) if operator == "=" else not bool(value)
        if operator not in ("=", "!="):
            return NotImplemented
        return overdue if wanted else ~overdue

    def action_send_invoice(self):
        """Email the posted invoice PDF once. A second call keeps the same message."""
        self.ensure_one()
        self._check_billing()
        if self.state != "posted" or not self.invoice_kind:
            raise UserError(self.env._("Only a posted invoice can be emailed."))
        key = f"invoice:{self.id}:sent"
        existing = self.env["mail.message"].sudo().search([("notification_key", "=", key)], limit=1)
        if existing:
            return existing
        pdf, _report_type = self.env["ir.actions.report"].sudo()._render_qweb_pdf("account.account_invoices", self.ids)
        attachment = self.env["ir.attachment"].create(
            {
                "name": f"{self.name or 'invoice'}.pdf",
                "raw": pdf,
                "res_model": self._name,
                "res_id": self.id,
                "mimetype": "application/pdf",
            }
        )
        return self.env["mail.message"].raise_event(
            EVENT_INVOICE_SENT,
            self,
            key,
            self.env._("Invoice %(name)s is attached.", name=self.name or ""),
            subject=self.name,
            partners=self.partner_id,
            attachments=attachment,
        )

    def button_draft(self):
        locked = self.filtered(lambda move: move.invoice_kind and move.state == "posted")
        if self.env.context.get("medilab_cancel_unpaid_advance"):
            locked = locked.filtered(lambda move: move.payment_state != "not_paid")
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

    def _get_invoice_legal_documents(self, filetype, allow_fallback=False):
        documents = super()._get_invoice_legal_documents(filetype, allow_fallback=allow_fallback)
        self._audit_legal_documents(documents)
        return documents

    def _get_invoice_legal_documents_all(self, allow_fallback=False):
        documents = super()._get_invoice_legal_documents_all(allow_fallback=allow_fallback)
        self._audit_legal_documents(documents)
        return documents

    def _audit_legal_documents(self, documents):
        # Odoo reads an invoice's legal documents only to serve them: from the portal, the Download action and the
        # export of journal entries.
        if documents:
            self._audit("download", ", ".join(document["filename"] for document in documents))

    def _report_paid_amount(self):
        self.ensure_one()
        return self.currency_id.round(self.amount_total - self.amount_residual)

    def _report_tax_amounts(self):
        """Tax collected on this invoice, one positive amount per tax line."""
        self.ensure_one()
        amounts = []
        for line in self.line_ids.filtered(lambda item: item.display_type == "tax"):
            amounts.append((line.name, abs(line.amount_currency or line.balance)))
        return amounts

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
