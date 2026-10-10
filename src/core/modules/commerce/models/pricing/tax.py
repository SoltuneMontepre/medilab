from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import format_date

from odoo.addons.commerce.constants.models import MODEL_TAX, MODEL_TAX_RATE
from odoo.addons.laboratory.constants.models import MODEL_ARCHIVE_MIXIN, MODEL_PERMISSION_MIXIN


# Thuế
class Tax(models.Model):
    _name = MODEL_TAX
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN]
    _description = "Tax"
    _order = "code"
    _rec_names_search = ("name", "code")

    # Unique code of the tax, such as VAT10 or KCT.
    code = fields.Char(required=True, copy=False)
    # Tax name as printed on quotations and invoices, in each language.
    name = fields.Char(required=True, translate=True)
    # False when the tax is archived.
    active = fields.Boolean(default=True)
    # The tax's rate over time.
    rate_ids = fields.One2many(MODEL_TAX_RATE, "tax_id", string="Rates")

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a tax must be unique.")

    def _rate_on(self, date):
        """Return the rate in percent in force on the date; refuse when no period covers it."""
        self.ensure_one()
        rate = self.env[MODEL_TAX_RATE].search(
            Domain("tax_id", "=", self.id)
            & Domain("valid_from", "<=", date)
            & (Domain("valid_until", "=", False) | Domain("valid_until", ">=", date)),
            limit=1,
        )
        if not rate:
            raise UserError(
                self.env._("%(tax)s has no rate on %(date)s.", tax=self.display_name, date=format_date(self.env, date))
            )
        return rate.rate
