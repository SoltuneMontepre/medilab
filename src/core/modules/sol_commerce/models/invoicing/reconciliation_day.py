from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import MODEL_PAYMENT_TRANSACTION, MODEL_RECONCILIATION_DAY
from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION_MIXIN

VIETNAM = ZoneInfo("Asia/Ho_Chi_Minh")


# Ngày đối soát
class ReconciliationDay(models.Model):
    _name = MODEL_RECONCILIATION_DAY
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Reconciliation Day"
    _order = "day desc"
    # The accountant opens a day, posts what is missing and locks it. A locked day stays locked.
    _permission_actions = ("read", "create", "edit")

    # The Vietnam calendar day being reconciled.
    day = fields.Date(required=True)
    # open until the accountant locks it.
    status = fields.Selection([("open", "Open"), ("locked", "Locked")], default="open", required=True)
    # The accountant who locked the day.
    locked_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    # When the day was locked.
    locked_at = fields.Datetime(readonly=True, copy=False)
    # PayOS transactions whose moment in Vietnam falls on this day.
    transaction_ids = fields.Many2many(MODEL_PAYMENT_TRANSACTION, compute="_compute_transaction_ids")
    # Confirmed PayOS transactions of the day that have no payment yet.
    missing_payment_count = fields.Integer(compute="_compute_transaction_ids")

    _day_unique = models.Constraint("UNIQUE(day)", "A day is reconciled once.")

    @api.depends("day")
    def _compute_transaction_ids(self):
        transactions = self.env[MODEL_PAYMENT_TRANSACTION]
        for record in self:
            if not record.day:
                record.transaction_ids = transactions
                record.missing_payment_count = 0
                continue
            found = transactions.search(
                [("provider_code", "=", "payos"), ("create_date", ">=", record._start()), ("create_date", "<", record._end())]
            )
            record.transaction_ids = found
            record.missing_payment_count = len(found.filtered(lambda tx: tx.state == "done" and not tx.payment_id))

    def action_post_missing_payments(self):
        """Post a payment for each confirmed PayOS transaction of the day that has none."""
        self.ensure_one()
        missing = self.transaction_ids.filtered(lambda tx: tx.state == "done" and not tx.payment_id)
        for transaction in missing:
            transaction._create_online_payment()
        return True

    def action_lock(self):
        self.ensure_one()
        if self.status == "locked":
            raise UserError(self.env._("This day is already locked."))
        self.write(
            {"status": "locked", "locked_by_id": self.env.user.id, "locked_at": fields.Datetime.now()}
        )
        return True

    def write(self, vals):
        if vals.get("status") == "open" and any(day.status == "locked" for day in self):
            raise UserError(self.env._("A locked day stays locked."))
        return super().write(vals)

    def _start(self):
        return datetime.combine(self.day, time.min, tzinfo=VIETNAM).astimezone(UTC).replace(tzinfo=None)

    def _end(self):
        return self._start() + timedelta(days=1)

    @api.model
    def _vietnam_day(self, moment):
        moment = moment or fields.Datetime.now()
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return moment.astimezone(VIETNAM).date()

    @api.model
    def _today_is_locked(self):
        return bool(self.search_count([("day", "=", self._vietnam_day(fields.Datetime.now())), ("status", "=", "locked")]))
