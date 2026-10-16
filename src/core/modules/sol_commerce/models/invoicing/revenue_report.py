from odoo import fields, models
from odoo.tools import SQL

from odoo.addons.sol_commerce.constants.models import (
    MODEL_ACCOUNT_MOVE,
    MODEL_ACCOUNT_MOVE_LINE,
    MODEL_PARAMETER_PRICE,
    MODEL_PRODUCT_PRODUCT,
    MODEL_PRODUCT_TEMPLATE,
    MODEL_REVENUE_REPORT,
    MODEL_SERVICE_PACKAGE_LINE,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_PARAMETER_GROUP,
    MODEL_PERMISSION_MIXIN,
    MODEL_RES_PARTNER,
    MODEL_TEST_PARAMETER,
)

# A parameter product sells its parameter whole. A package line is spread over the package's parameters by their own
# prices times quantities, as the package's price of its parts counts them, or by quantities when none has a price.
# Each part is the rounded running total minus the rounded running total before it, so the parts add up to the line
# exactly. A row is one part of one invoice line.
# ponytail: spreads by the package's parameters and prices of today; store the parts on the invoice line if past
# revenue must not move when a package or a price changes.
QUERY = """
WITH parts AS (
    SELECT template.id AS template_id, template.parameter_id, 1::numeric AS quantity, 1::numeric AS weight
      FROM product_template template
     WHERE template.parameter_id IS NOT NULL
    UNION ALL
    SELECT template.id, line.parameter_id, line.quantity::numeric, line.quantity * COALESCE(price.list_price, 0)
      FROM product_template template
      JOIN medilab_service_package_line line ON line.package_id = template.service_package_id
      LEFT JOIN medilab_parameter_price price ON price.parameter_id = line.parameter_id AND price.active
),
bases AS (
    SELECT parts.*,
           CASE WHEN SUM(weight) OVER (PARTITION BY template_id) > 0 THEN weight ELSE quantity END AS basis
      FROM parts
),
shares AS (
    SELECT template_id, parameter_id, ROW_NUMBER() OVER running AS part,
           SUM(basis) OVER running / SUM(basis) OVER whole AS share_to,
           (SUM(basis) OVER running - basis) / SUM(basis) OVER whole AS share_from
      FROM bases
    WINDOW whole AS (PARTITION BY template_id), running AS (PARTITION BY template_id ORDER BY parameter_id)
),
lines AS (
    SELECT item.id::bigint * 1000 + COALESCE(share.part, 0) AS id, share.parameter_id, move.name,
           move.invoice_date AS date, move.commercial_partner_id AS partner_id, company.currency_id,
           ROUND(-item.balance * COALESCE(share.share_to, 1), currency.decimal_places)
               - ROUND(-item.balance * COALESCE(share.share_from, 0), currency.decimal_places) AS invoiced,
           (move.amount_total_signed - move.amount_residual_signed) / NULLIF(move.amount_total_signed, 0) AS paid_share
      FROM account_move_line item
      JOIN account_move move ON move.id = item.move_id
      JOIN res_company company ON company.id = move.company_id
      JOIN res_currency currency ON currency.id = company.currency_id
      LEFT JOIN product_product product ON product.id = item.product_id
      LEFT JOIN shares share ON share.template_id = product.product_tmpl_id
     WHERE move.state = 'posted'
       AND move.move_type IN ('out_invoice', 'out_refund')
       AND move.invoice_kind IS NOT NULL
       AND item.display_type = 'product'
)
SELECT lines.id, lines.name, lines.date, lines.partner_id, lines.currency_id, lines.parameter_id,
       parameter.main_group_id AS group_id, lines.invoiced,
       lines.invoiced * COALESCE(lines.paid_share, 0) AS collected
  FROM lines
  LEFT JOIN medilab_test_parameter parameter ON parameter.id = lines.parameter_id
"""


# Báo Cáo Doanh Thu
class RevenueReport(models.Model):
    _name = MODEL_REVENUE_REPORT
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Revenue"
    _auto = False
    _order = "date desc, id"
    _permission_actions = ("read",)
    _depends = {
        MODEL_ACCOUNT_MOVE: [
            "amount_residual_signed",
            "amount_total_signed",
            "commercial_partner_id",
            "company_id",
            "invoice_date",
            "invoice_kind",
            "move_type",
            "name",
            "state",
        ],
        MODEL_ACCOUNT_MOVE_LINE: ["balance", "display_type", "move_id", "product_id"],
        MODEL_PRODUCT_PRODUCT: ["product_tmpl_id"],
        MODEL_PRODUCT_TEMPLATE: ["parameter_id", "service_package_id"],
        MODEL_SERVICE_PACKAGE_LINE: ["package_id", "parameter_id", "quantity"],
        MODEL_PARAMETER_PRICE: ["active", "list_price", "parameter_id"],
        MODEL_TEST_PARAMETER: ["main_group_id"],
    }

    # Number of the invoice or credit note.
    name = fields.Char(string="Invoice", readonly=True)
    # Date of the invoice; the period the revenue counts in.
    date = fields.Date(readonly=True)
    # The customer billed.
    partner_id = fields.Many2one(MODEL_RES_PARTNER, string="Customer", readonly=True)
    # Currency of the company.
    currency_id = fields.Many2one("res.currency", readonly=True)
    # The parameter the revenue is for; empty for an advance, its deduction and an adjustment.
    parameter_id = fields.Many2one(MODEL_TEST_PARAMETER, readonly=True)
    # Main group of the parameter.
    group_id = fields.Many2one(MODEL_PARAMETER_GROUP, string="Main Group", readonly=True)
    # Invoiced amount excluding VAT; negative on a credit note and on the advance deducted from a final invoice.
    invoiced = fields.Monetary(readonly=True)
    # The share of the invoiced amount that confirmed payments have settled.
    collected = fields.Monetary(readonly=True)

    @property
    def _table_sql(self):
        # The query replaces the table; Odoo's table SQL carries the _depends fields to save before reading.
        return SQL("(%s)", SQL(QUERY), to_flush=super()._table_sql._sql_tuple[2])
