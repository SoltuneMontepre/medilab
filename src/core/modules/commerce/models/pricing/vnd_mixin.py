from odoo import api, fields, models

from odoo.addons.commerce.constants.models import MODEL_VND_MIXIN
from odoo.addons.commerce.constants.xml_ids import VND


# Gives money fields their currency: every price is in VND.
class VndMixin(models.AbstractModel):
    _name = MODEL_VND_MIXIN
    _description = "Prices in VND"

    # The currency of the money fields, always VND.
    currency_id = fields.Many2one("res.currency", compute="_compute_currency_id")

    def _compute_currency_id(self):
        self.currency_id = self.env.ref(VND)

    @api.model_create_multi
    def create(self, vals_list):
        # Odoo rounds money on insert only through a stored currency field, so new amounts are rounded here.
        vnd = self.env.ref(VND)
        for vals in vals_list:
            for name, value in vals.items():
                if self._fields[name].type == "monetary":
                    vals[name] = vnd.round(value)
        return super().create(vals_list)
