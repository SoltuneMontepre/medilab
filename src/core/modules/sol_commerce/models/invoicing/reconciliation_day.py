from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import MODEL_PAYMENT_TRANSACTION, MODEL_RECONCILIATION_DAY
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_PERMISSION_MIXIN

VIETNAM = ZoneInfo("Asia/Ho_Chi_Minh")


# Ngày đối soát
class ReconciliationDay(models.Model):
    _name = MODEL_RECONCILIATION_DAY
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
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
    # The accountant accepts overpayments or amount differences and may then lock the day.
    discrepancies_acknowledged = fields.Boolean(copy=False)
    # PayOS transactions whose transfer time in Vietnam falls on this day.
    transaction_ids = fields.Many2many(MODEL_PAYMENT_TRANSACTION, compute="_compute_transaction_ids")
    # Confirmed PayOS transactions of the day that have no payment yet.
    missing_payment_count = fields.Integer(compute="_compute_transaction_ids")
    # Payments whose amount is not the transfer, or that are more than the invoice.
    mismatch_count = fields.Integer(compute="_compute_transaction_ids")
    # Company currency of the printed totals.
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)
    # Sum of confirmed PayOS transfers on this day.
    transfer_total = fields.Monetary(
        string="Transfer total", compute="_compute_transaction_ids", currency_field="currency_id"
    )
    # Sum of the payments recorded for those transfers.
    payment_total = fields.Monetary(
        string="Payment total", compute="_compute_transaction_ids", currency_field="currency_id"
    )
    # Confirmed transfers minus the payments recorded for them.
    difference_total = fields.Monetary(
        string="Difference", compute="_compute_transaction_ids", currency_field="currency_id"
    )

    _day_unique = models.Constraint("UNIQUE(day)", "A day is reconciled once.")

    @api.depends("day")
    def _compute_transaction_ids(self):
        transactions = self.env[MODEL_PAYMENT_TRANSACTION]
        for record in self:
            if not record.day:
                record.transaction_ids = transactions
                record.missing_payment_count = 0
                record.mismatch_count = 0
                record.transfer_total = 0
                record.payment_total = 0
                record.difference_total = 0
                continue
            found = transactions.search(
                [
                    ("provider_code", "=", "payos"),
                    ("payos_transferred_at", ">=", record._start()),
                    ("payos_transferred_at", "<", record._end()),
                ]
            )
            confirmed = found.filtered(lambda tx: tx.state == "done")
            record.transaction_ids = found
            record.missing_payment_count = len(confirmed.filtered(lambda tx: not tx.payment_id))
            record.mismatch_count = len(found.filtered(record._amount_mismatch))
            record.transfer_total = sum(confirmed.mapped("amount"))
            record.payment_total = sum(confirmed.mapped("payment_id.amount"))
            record.difference_total = record.transfer_total - record.payment_total

    def action_post_missing_payments(self):
        """Post a payment for each confirmed PayOS transaction of the day that has none."""
        self.ensure_one()
        missing = self.transaction_ids.filtered(lambda tx: tx.state == "done" and not tx.payment_id)
        for transaction in missing:
            transaction._create_online_payment()
        self.invalidate_recordset(["transaction_ids", "missing_payment_count", "mismatch_count"])
        return True

    def action_lock(self):
        self.ensure_one()
        if self.status == "locked":
            raise UserError(self.env._("This day is already locked."))
        self.invalidate_recordset(["transaction_ids", "missing_payment_count", "mismatch_count"])
        if self.missing_payment_count:
            raise UserError(self.env._("Post the missing payments before locking this day."))
        if self.mismatch_count and not self.discrepancies_acknowledged:
            raise UserError(self.env._("Acknowledge the amount differences before locking this day."))
        self.write({"status": "locked", "locked_by_id": self.env.user.id, "locked_at": fields.Datetime.now()})
        return True

    def action_print(self):
        """Print this day's PayOS totals. The report action is read for the accountant."""
        self.ensure_one()
        self.check_access("read")
        return self.env.ref("sol_commerce.action_report_reconciliation_day").sudo().report_action(self)

    def _amount_mismatch(self, transaction):
        payment = transaction.payment_id
        if transaction.state != "done" or not payment:
            return False
        return payment.exceeds_residual or payment.amount != transaction.amount

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
    def _day_is_locked(self, day):
        if not day:
            return False
        return bool(self.sudo().search_count([("day", "=", day), ("status", "=", "locked")]))

    @api.model
    def _payos_moment(self, value):
        """PayOS transactionDateTime is Vietnam local time. Store it as UTC."""
        if not isinstance(value, str) or not value:
            return False
        naive = False
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                naive = datetime.strptime(value[:19], pattern)
                break
            except ValueError:
                continue
        if not naive:
            return False
        return naive.replace(tzinfo=VIETNAM).astimezone(UTC).replace(tzinfo=None)
