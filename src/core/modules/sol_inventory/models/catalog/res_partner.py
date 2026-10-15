from odoo import api, fields, models

from odoo.addons.sol_inventory.constants.models import MODEL_SUPPLIER, MODEL_SUPPLIER_INFO
from odoo.addons.sol_laboratory.constants.models import MODEL_RES_PARTNER


# Liên Hệ
class ResPartner(models.Model):
    _inherit = MODEL_RES_PARTNER

    # Suppliers whose company contact this is.
    supplier_ids = fields.One2many(MODEL_SUPPLIER, "partner_id", string="Suppliers")
    # The items the contact sells as a supplier, with its references and last prices.
    supplier_item_ids = fields.One2many(MODEL_SUPPLIER_INFO, "partner_id", string="Supplied Items")

    @api.depends("supplier_ids")
    def _compute_is_company(self):
        # A supplier's contact is a company even without a tax ID, as a subcontractor's is.
        result = super()._compute_is_company()
        for partner in self.filtered("supplier_ids"):
            partner.is_company = True
        return result
