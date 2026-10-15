from odoo import fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_RES_COMPANY
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN


# Công Ty
class ResCompany(models.Model):
    _name = MODEL_RES_COMPANY
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_RES_COMPANY]

    # A quotation is accepted by paying its advance or from the portal, so the customer never signs online.
    portal_confirmation_sign = fields.Boolean(default=False)
