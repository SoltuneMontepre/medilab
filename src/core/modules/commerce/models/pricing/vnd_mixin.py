from odoo import fields, models

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
