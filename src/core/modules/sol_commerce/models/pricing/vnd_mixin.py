from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_VND_MIXIN
from odoo.addons.sol_commerce.constants.xml_ids import VND

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_vnd_mixin as VndMixinBase
else:
    VndMixinBase = object


# Gives money fields their currency: every price is in VND.
class VndMixin(models.AbstractModel, VndMixinBase):
    _name = MODEL_VND_MIXIN
    _description = "Prices in VND"

    if not TYPE_CHECKING:
        # The currency of the money fields, always VND; stored so that Odoo rounds amounts and sums them in groups.
        currency_id = fields.Many2one(
            "res.currency", required=True, readonly=True, default=lambda self: self.env.ref(VND)
        )
