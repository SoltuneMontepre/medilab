from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_list

from odoo.addons.commerce.constants.models import (
    MODEL_PAYMENT_LINK_TRANSACTION,
    MODEL_RECONCILIATION_DAY,
    MODEL_VND_MIXIN,
)
from odoo.addons.commerce.constants.xml_ids import REPORT_RECONCILIATION_DAY
from odoo.addons.commerce.models.invoicing.payment_link import PROVIDER_UPDATE_KEY
from odoo.addons.laboratory.constants.models import MODEL_PERMISSION_MIXIN


# Ngày Đối Soát
class ReconciliationDay(models.Model):
    _name = MODEL_RECONCILIATION_DAY
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_VND_MIXIN]
    _description = "Reconciliation Day"
    _order = "day desc"
    _rec_name = "day"
    # A day is opened and locked by the accountant; a locked day is never deleted.
    _permission_actions = ("read", "create", "edit")

    # The day reconciled: the Vietnam day of the PayOS transfers.
    day = fields.Date(required=True, default=fields.Date.context_today, index=True)
    # open or locked.
    status = fields.Selection([("open", "Open"), ("locked", "Locked")], required=True, default="open", index=True)
    # The accountant who locked the day.
    locked_by_id = fields.Many2one("res.users", string="Locked by", readonly=True, ondelete="restrict")
    # When the day was locked.
    locked_at = fields.Datetime(readonly=True)
    # The PayOS transfers of the day.
    transaction_ids = fields.One2many(MODEL_PAYMENT_LINK_TRANSACTION, "day_id", string="Transactions")
    # Sum of the day's PayOS transfers.
    total_amount = fields.Monetary(compute="_compute_counts")
    # Transfers of the day.
    transaction_count = fields.Integer(compute="_compute_counts")
    # Transfers without their payment; they block the lock until Record payments creates it.
    blocking_count = fields.Integer(compute="_compute_counts")
    # Rows whose underpaid link or overpaying payment still lacks an acknowledgement; they block the lock too.
    unacknowledged_count = fields.Integer(compute="_compute_counts")

    _day_unique = models.Constraint("UNIQUE(day)", "This day is already being reconciled.")

    @api.model_create_multi
    def create(self, vals_list):
        days = super().create(vals_list)
        # The transfers of the day reported before it was opened join it; later ones join as they are stored.
        transactions = self.env[MODEL_PAYMENT_LINK_TRANSACTION].sudo()
        for day in days:
            transactions.search([("transacted_date", "=", day.day), ("day_id", "=", False)]).write({"day_id": day.id})
        return days

    @api.depends("transaction_ids.amount", "transaction_ids.match_state", "transaction_ids.needs_acknowledgement")
    def _compute_counts(self):
        for day in self:
            transactions = day.transaction_ids
            day.total_amount = day.currency_id.round(sum(transactions.mapped("amount")))
            day.transaction_count = len(transactions)
            day.blocking_count = len(transactions.filtered(lambda transaction: not transaction.payment_id))
            day.unacknowledged_count = len(transactions.filtered("needs_acknowledgement"))

    def write(self, vals):
        locked = self.filtered(lambda day: day.status == "locked")
        if locked:
            raise UserError(
                self.env._("A locked day is never changed: %s", format_list(self.env, locked.mapped("display_name")))
            )
        if "day" in vals:
            raise UserError(self.env._("The day of a reconciliation cannot change; open another day instead."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_locked(self):
        locked = self.filtered(lambda day: day.status == "locked")
        if locked:
            raise UserError(
                self.env._("A locked day is never deleted: %s", format_list(self.env, locked.mapped("display_name")))
            )

    def action_lock(self):
        self._check_permission("edit")
        for day in self:
            if day.status != "open":
                raise UserError(self.env._("%s is already locked.", day.display_name))
            problems = [
                self.env._("%s: no payment recorded; use Record payments", transaction.reference)
                for transaction in day.transaction_ids
                if not transaction.payment_id
            ] + [
                self.env._(
                    "%(reference)s: %(state)s, to be acknowledged",
                    reference=transaction.reference,
                    state=transaction.match_state,
                )
                for transaction in day.transaction_ids
                if transaction.needs_acknowledgement
            ]
            if problems:
                raise UserError(self.env._("The day cannot be locked yet:\n%s", "\n".join(problems)))
            day.write({"status": "locked", "locked_by_id": self.env.user.id, "locked_at": fields.Datetime.now()})

    def action_print(self):
        return self.env.ref(REPORT_RECONCILIATION_DAY).sudo().report_action(self, config=False)

    @api.model
    def _locked_days(self, days):
        return set(self.sudo().search([("status", "=", "locked"), ("day", "in", list(days))]).mapped("day"))

    @api.model
    def _check_unlocked(self, days, what):
        """Refuse a change on a locked day, unless it comes from PayOS itself (the provider update context)."""
        if self.env.context.get(PROVIDER_UPDATE_KEY):
            return
        locked = self._locked_days(set(days))
        if locked:
            raise UserError(
                self.env._(
                    "%(what)s of a locked reconciliation day cannot be changed: %(days)s",
                    what=what,
                    days=format_list(self.env, [fields.Date.to_string(day) for day in sorted(locked)]),
                )
            )
