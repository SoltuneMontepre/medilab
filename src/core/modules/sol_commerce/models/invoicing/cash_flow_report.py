from typing import TYPE_CHECKING

from odoo import fields, models
from odoo.tools import SQL

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_MOVE, MODEL_ACCOUNT_PAYMENT, MODEL_CASH_FLOW_REPORT
from odoo.addons.sol_commerce.models.invoicing.account_payment import CONFIRMED_STATES, METHOD_SELECTION
from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION_MIXIN, MODEL_RES_PARTNER, MODEL_RES_USERS

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_cash_flow_report as CashFlowReportBase
else:
    CashFlowReportBase = object

QUERY = """
SELECT payment.id, payment.name, payment.date, partner.commercial_partner_id AS partner_id, payment.method,
       payment.amount_company_currency_signed AS amount, company.currency_id, payment.create_uid AS user_id,
       CASE WHEN payment.state = 'draft' THEN 'pending' ELSE 'confirmed' END AS status,
       (SELECT STRING_AGG(move.name, ', ' ORDER BY move.name)
          FROM account_move__account_payment link
          JOIN account_move move ON move.id = link.invoice_id
         WHERE link.payment_id = payment.id) AS invoices
  FROM account_payment payment
  JOIN res_company company ON company.id = payment.company_id
  LEFT JOIN res_partner partner ON partner.id = payment.partner_id
 WHERE payment.method IS NOT NULL
   AND payment.payment_type = 'inbound'
   AND (payment.state = 'draft' OR payment.state IN %(confirmed_states)s)
"""


# Báo Cáo Dòng Tiền
class CashFlowReport(models.Model, CashFlowReportBase):
    _name = MODEL_CASH_FLOW_REPORT
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Cash Flow"
    _auto = False
    _order = "date desc, id desc"
    _permission_actions = ("read",)
    _depends = {
        MODEL_ACCOUNT_PAYMENT: [
            "amount_company_currency_signed",
            "company_id",
            "date",
            "invoice_ids",
            "method",
            "name",
            "partner_id",
            "payment_type",
            "state",
        ],
        MODEL_ACCOUNT_MOVE: ["name"],
        MODEL_RES_PARTNER: ["commercial_partner_id"],
    }

    if not TYPE_CHECKING:
        # Receipt number, once the payment is confirmed.
        name = fields.Char(string="Receipt", readonly=True)
        # Date the money was received.
        date = fields.Date(readonly=True)
        # The customer who paid.
        partner_id = fields.Many2one(MODEL_RES_PARTNER, string="Customer", readonly=True)
        # Online, bank transfer or cash.
        method = fields.Selection(METHOD_SELECTION, string="Payment Method", readonly=True)
        # Amount received, in the company's currency.
        amount = fields.Monetary(readonly=True)
        # Currency of the company.
        currency_id = fields.Many2one("res.currency", readonly=True)
        # Who recorded the payment.
        user_id = fields.Many2one(MODEL_RES_USERS, string="Recorded By", readonly=True)
        # Pending until the accountant confirms the payment, then confirmed.
        status = fields.Selection([("pending", "Pending"), ("confirmed", "Confirmed")], readonly=True)
        # Numbers of the invoices paid.
        invoices = fields.Char(readonly=True)

    @property
    def _table_sql(self):
        # The query replaces the table; Odoo's table SQL carries the _depends fields to save before reading.
        query = SQL(QUERY, confirmed_states=CONFIRMED_STATES)
        return SQL("(%s)", query, to_flush=super()._table_sql._sql_tuple[2])
