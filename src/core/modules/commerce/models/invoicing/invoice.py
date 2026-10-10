from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain
from odoo.tools import format_list

from odoo.addons.commerce.constants.models import (
    MODEL_INVOICE,
    MODEL_INVOICE_LINE,
    MODEL_PAYMENT_LINK,
    MODEL_VND_MIXIN,
)
from odoo.addons.commerce.constants.xml_ids import REPORT_INVOICE
from odoo.addons.commerce.models.system.res_config_settings import INVOICE_DUE_DAYS
from odoo.addons.laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_IR_SEQUENCE,
    MODEL_PERMISSION_MIXIN,
    MODEL_RES_CONFIG_SETTINGS,
)

# Fields other features still write once an invoice is posted: when it was emailed and its stored PDF.
POSTED_WRITABLE_FIELDS = {"sent_at", "attachment_id"}


# Hóa Đơn
class Invoice(models.Model):
    _name = MODEL_INVOICE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_VND_MIXIN]
    _description = "Invoice"
    _order = "posted_at desc, id desc"

    # Unique invoice number; filled from the sequence when the invoice is posted.
    code = fields.Char(readonly=True, copy=False, index=True)
    # The contact billed: the customer, or one of its people.
    partner_id = fields.Many2one("res.partner", string="Customer", required=True, ondelete="restrict", index=True)
    # advance, final or adjustment.
    kind = fields.Selection(
        [("advance", "Advance"), ("final", "Final"), ("adjustment", "Adjustment")], required=True, default="final"
    )
    # draft, posted or cancelled.
    status = fields.Selection(
        [("draft", "Draft"), ("posted", "Posted"), ("cancelled", "Cancelled")],
        required=True,
        default="draft",
        index=True,
        copy=False,
    )
    # When the invoice was posted.
    posted_at = fields.Datetime(readonly=True, copy=False)
    # When the invoice must be paid.
    due_date = fields.Date()
    # The invoice an adjustment invoice corrects; empty for other invoices.
    adjusts_id = fields.Many2one(MODEL_INVOICE, string="Corrects", ondelete="restrict", index=True)
    # Adjustment invoices that correct this invoice.
    adjustment_ids = fields.One2many(MODEL_INVOICE, "adjusts_id", string="Adjustments")
    # Lines of the invoice.
    line_ids = fields.One2many(MODEL_INVOICE_LINE, "invoice_id", string="Lines")
    # Online payment links asking PayOS for the invoice's amounts.
    payment_link_ids = fields.One2many(MODEL_PAYMENT_LINK, "invoice_id", string="Payment links")
    # Total excluding VAT.
    amount_untaxed = fields.Monetary(compute="_compute_amounts", store=True)
    # Total VAT.
    amount_tax = fields.Monetary(compute="_compute_amounts", store=True)
    # Total including VAT; negative for an adjustment that lowers the amount.
    amount_total = fields.Monetary(compute="_compute_amounts", store=True)
    # Sum of the totals of the posted adjustment invoices that correct this invoice.
    amount_adjustment = fields.Monetary(compute="_compute_amount_adjustment", store=True)
    # What the customer still owes on the invoice: its total and its adjustments; 0 on an adjustment invoice itself.
    amount_owed = fields.Monetary(compute="_compute_amount_owed", store=True)
    # When the invoice was last emailed to the customer.
    sent_at = fields.Datetime(readonly=True, copy=False)
    # The invoice's PDF, stored when it is emailed.
    attachment_id = fields.Many2one("ir.attachment", readonly=True, copy=False, ondelete="set null")

    _code_unique = models.Constraint("UNIQUE(code)", "An invoice with this number already exists.")

    @api.depends("line_ids.amount_untaxed", "line_ids.amount_tax")
    def _compute_amounts(self):
        for invoice in self:
            invoice.amount_untaxed = invoice.currency_id.round(sum(invoice.line_ids.mapped("amount_untaxed")))
            invoice.amount_tax = invoice.currency_id.round(sum(invoice.line_ids.mapped("amount_tax")))
            invoice.amount_total = invoice.amount_untaxed + invoice.amount_tax

    @api.depends("adjustment_ids.status", "adjustment_ids.amount_total")
    def _compute_amount_adjustment(self):
        for invoice in self:
            posted = invoice.adjustment_ids.filtered(lambda adjustment: adjustment.status == "posted")
            invoice.amount_adjustment = invoice.currency_id.round(sum(posted.mapped("amount_total")))

    @api.depends("kind", "amount_total", "amount_adjustment")
    def _compute_amount_owed(self):
        for invoice in self:
            invoice.amount_owed = (
                0 if invoice.kind == "adjustment" else invoice.amount_total + invoice.amount_adjustment
            )

    @api.depends("code", "kind")
    def _compute_display_name(self):
        kinds = dict(self._fields["kind"]._description_selection(self.env))
        for invoice in self:
            invoice.display_name = invoice.code or self.env._("Draft %s invoice", kinds[invoice.kind].lower())

    @api.constrains("kind", "adjusts_id", "partner_id")
    def _check_adjustment(self):
        for invoice in self:
            if (invoice.kind == "adjustment") != bool(invoice.adjusts_id):
                raise ValidationError(
                    self.env._("An adjustment invoice corrects a posted invoice, and only an adjustment invoice does.")
                )
            corrected = invoice.adjusts_id
            if corrected and (
                corrected.kind == "adjustment"
                or corrected.status != "posted"
                or corrected.partner_id != invoice.partner_id
            ):
                raise ValidationError(
                    self.env._("An adjustment invoice corrects a posted advance or final invoice of the same customer.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        # Lines are created after their invoice, so an invoice created posted or cancelled takes its status last.
        statuses = [vals.pop("status", "draft") for vals in vals_list]
        invoices = super().create(vals_list)
        for invoice, status in zip(invoices, statuses, strict=True):
            if status != "draft":
                invoice.write({"status": status})
        return invoices

    def write(self, vals):
        frozen = self.filtered(lambda invoice: invoice.status != "draft")
        if frozen and set(vals) - POSTED_WRITABLE_FIELDS:
            raise UserError(
                self.env._(
                    "%s cannot be changed once posted or cancelled; correct a posted invoice with an adjustment invoice.",
                    format_list(self.env, frozen.mapped("display_name")),
                )
            )
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_posted(self):
        posted = self.filtered(lambda invoice: invoice.status == "posted")
        if posted:
            raise UserError(
                self.env._(
                    "A posted invoice is never deleted: %s", format_list(self.env, posted.mapped("display_name"))
                )
            )

    def _in_use_domain(self):
        return Domain("status", "=", "draft")

    def _check_lines_editable(self):
        frozen = self.filtered(lambda invoice: invoice.status != "draft")
        if frozen:
            raise UserError(self.env._("The lines of a posted or cancelled invoice cannot be changed."))

    def action_post(self):
        self._check_permission("edit")
        for invoice in self:
            invoice._check_postable()
            posting_date = fields.Date.context_today(invoice)
            due_days = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter(INVOICE_DUE_DAYS)
            invoice.write(
                {
                    "status": "posted",
                    "posted_at": fields.Datetime.now(),
                    "due_date": invoice.due_date or posting_date + timedelta(days=due_days),
                    "code": self.env[MODEL_IR_SEQUENCE].next_by_code(MODEL_INVOICE, sequence_date=posting_date),
                }
            )

    def _check_postable(self):
        self.ensure_one()
        if self.status != "draft":
            raise UserError(self.env._("Only a draft invoice can be posted."))
        if not self.line_ids:
            raise UserError(self.env._("Add at least one line before posting the invoice."))
        if self.kind == "adjustment":
            if self.currency_id.is_zero(self.amount_total):
                raise UserError(
                    self.env._("An adjustment invoice holds the difference it makes; its total cannot be 0.")
                )
            if self.currency_id.compare_amounts(self.adjusts_id.amount_owed + self.amount_total, 0) < 0:
                raise UserError(
                    self.env._("The adjustment takes %s below what is paid or owed.", self.adjusts_id.display_name)
                )
        elif self.currency_id.compare_amounts(self.amount_total, 0) < 0:
            raise UserError(self.env._("An advance or final invoice cannot have a negative total."))

    def action_cancel(self):
        self._check_permission("edit")
        if any(invoice.status != "draft" for invoice in self):
            raise UserError(
                self.env._("Only a draft invoice can be cancelled; correct a posted one with an adjustment.")
            )
        self.write({"status": "cancelled"})

    def action_create_adjustment(self):
        self.ensure_one()
        self._check_permission("create")
        if self.status != "posted" or self.kind == "adjustment":
            raise UserError(self.env._("An adjustment corrects a posted advance or final invoice."))
        adjustment = self.create(
            {
                "kind": "adjustment",
                "adjusts_id": self.id,
                "partner_id": self.partner_id.id,
                "line_ids": [
                    Command.create(
                        {"description": self.env._("Adjustment of %s", self.code), "amount_untaxed": 0, "tax_rate": 0}
                    )
                ],
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": MODEL_INVOICE,
            "res_id": adjustment.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_create_payment_link(self):
        self.ensure_one()
        link = self.env[MODEL_PAYMENT_LINK]._create_for_invoice(self, self.amount_owed)
        return {
            "type": "ir.actions.act_window",
            "res_model": MODEL_PAYMENT_LINK,
            "res_id": link.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_print(self):
        # config=False skips Odoo's layout configurator; the laboratory header comes from the theme.
        return self.env.ref(REPORT_INVOICE).report_action(self, config=False)

    def tax_totals_by_rate(self):
        """The net and tax amounts per tax rate, from the lines' rounded amounts, so they add up to the totals."""
        self.ensure_one()
        totals = {}
        for line in self.line_ids:
            untaxed, tax = totals.get(line.tax_rate, (0.0, 0.0))
            totals[line.tax_rate] = (untaxed + line.amount_untaxed, tax + line.amount_tax)
        return [(rate, untaxed, tax) for rate, (untaxed, tax) in sorted(totals.items())]
