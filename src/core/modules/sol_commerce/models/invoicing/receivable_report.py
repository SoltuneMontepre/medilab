from datetime import datetime

from odoo import fields, models
from odoo.tools import SQL

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_MOVE, MODEL_ACCOUNT_PAYMENT, MODEL_RECEIVABLE_REPORT
from odoo.addons.sol_commerce.constants.orders import ADVANCE_PAID_STATES
from odoo.addons.sol_commerce.models.invoicing.account_move import VIETNAM
from odoo.addons.sol_commerce.models.invoicing.account_payment import CONFIRMED_STATES
from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION_MIXIN, MODEL_RES_PARTNER

AGES = [
    ("not_due", "Not due"),
    ("1_30", "1-30 days"),
    ("31_60", "31-60 days"),
    ("61_90", "61-90 days"),
    ("over_90", "Over 90 days"),
]

# An invoice is paid on the date of its last confirmed payment, and its debt ages from its due date. One cleared by a
# credit note has no payment and is neither on time nor late.
QUERY = """
WITH invoices AS (
    SELECT move.id, move.name, move.commercial_partner_id AS partner_id, company.currency_id,
           move.invoice_date AS date, move.invoice_date_due AS date_due,
           (move.sent_at AT TIME ZONE 'UTC' AT TIME ZONE %(zone)s)::date AS sent_date,
           move.amount_total_signed AS amount_total, move.amount_residual_signed AS amount_owed,
           CASE WHEN move.amount_residual_signed > 0 THEN GREATEST(%(today)s - move.invoice_date_due, 0) END
               AS days_overdue,
           CASE WHEN move.payment_state IN %(paid_states)s THEN paid.date END AS paid_date
      FROM account_move move
      JOIN res_company company ON company.id = move.company_id
      LEFT JOIN LATERAL (
          SELECT MAX(payment.date) AS date
            FROM account_move__account_payment link
            JOIN account_payment payment ON payment.id = link.payment_id
           WHERE link.invoice_id = move.id AND payment.state IN %(confirmed_states)s
      ) paid ON TRUE
     WHERE move.state = 'posted' AND move.move_type = 'out_invoice' AND move.invoice_kind IS NOT NULL
),
timed AS (
    SELECT invoices.*,
           CASE WHEN paid_date <= date_due THEN 'on_time'
                WHEN paid_date > date_due OR days_overdue > 0 THEN 'late' END AS timing
      FROM invoices
)
SELECT timed.*,
       CASE WHEN days_overdue = 0 THEN 'not_due'
            WHEN days_overdue <= 30 THEN '1_30'
            WHEN days_overdue <= 60 THEN '31_60'
            WHEN days_overdue <= 90 THEN '61_90'
            WHEN days_overdue > 90 THEN 'over_90' END AS age,
       paid_date - sent_date AS days_to_pay,
       CASE timing WHEN 'on_time' THEN 100 WHEN 'late' THEN 0 END AS paid_on_time
  FROM timed
"""


# Báo Cáo Công Nợ
class ReceivableReport(models.Model):
    _name = MODEL_RECEIVABLE_REPORT
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Receivables"
    _auto = False
    _order = "date_due, id"
    _permission_actions = ("read",)
    _depends = {
        MODEL_ACCOUNT_MOVE: [
            "amount_residual_signed",
            "amount_total_signed",
            "commercial_partner_id",
            "company_id",
            "invoice_date",
            "invoice_date_due",
            "invoice_kind",
            "move_type",
            "name",
            "payment_state",
            "sent_at",
            "state",
        ],
        MODEL_ACCOUNT_PAYMENT: ["date", "invoice_ids", "state"],
    }

    # Number of the invoice.
    name = fields.Char(string="Invoice", readonly=True)
    # The customer billed.
    partner_id = fields.Many2one(MODEL_RES_PARTNER, string="Customer", readonly=True)
    # Currency of the company.
    currency_id = fields.Many2one("res.currency", readonly=True)
    # Date of the invoice; the period the invoice counts in.
    date = fields.Date(readonly=True)
    # When the invoice must be paid.
    date_due = fields.Date(string="Due Date", readonly=True)
    # The day in Vietnam the invoice went to the customer.
    sent_date = fields.Date(readonly=True)
    # Total including VAT.
    amount_total = fields.Monetary(string="Total", readonly=True)
    # What confirmed payments have not settled yet.
    amount_owed = fields.Monetary(string="Owed", readonly=True)
    # Days past the due date while something is owed; 0 before it, empty once paid.
    days_overdue = fields.Integer(readonly=True, aggregator="avg")
    # Not due, 1-30, 31-60, 61-90 or over 90 days past the due date while something is owed.
    age = fields.Selection(AGES, string="Age of the Debt", readonly=True)
    # The day of the last confirmed payment of a paid invoice.
    paid_date = fields.Date(readonly=True)
    # Days from sending the invoice to its last confirmed payment.
    days_to_pay = fields.Integer(readonly=True, aggregator="avg")
    # On time when paid by the due date, late when paid after it or still open after it; empty until then.
    timing = fields.Selection([("on_time", "On time"), ("late", "Late")], string="Payment", readonly=True)
    # 100 for an invoice paid on time and 0 for a late one. Averaged, it is the share of invoices paid on time.
    paid_on_time = fields.Float(string="Paid on Time (%)", readonly=True, aggregator="avg", digits=(16, 1))

    @property
    def _table_sql(self):
        # The query replaces the table; Odoo's table SQL carries the _depends fields to save before reading.
        query = SQL(
            QUERY,
            today=datetime.now(VIETNAM).date(),
            zone=VIETNAM.key,
            paid_states=ADVANCE_PAID_STATES,
            confirmed_states=CONFIRMED_STATES,
        )
        return SQL("(%s)", query, to_flush=super()._table_sql._sql_tuple[2])
